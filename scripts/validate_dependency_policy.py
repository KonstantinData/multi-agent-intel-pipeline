"""Validate dependency license policy, direct-dependency registry, and CVE exception expiry."""

from __future__ import annotations

import importlib.metadata
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_DIR = ROOT / "policies" / "license"
_LOCK_PKG = re.compile(r"^([A-Za-z0-9_.\-]+)==")


def _load(name: str) -> dict:
    return json.loads((POLICY_DIR / name).read_text(encoding="utf-8"))


# Maps common free-text variants to their SPDX identifier.
# Keys are lowercase-stripped; values are canonical SPDX strings.
_LICENSE_ALIASES: dict[str, str] = {
    # MIT
    "mit license": "MIT",
    "mit licence": "MIT",
    "the mit license": "MIT",
    "the mit license (mit)": "MIT",
    "mit/x11": "MIT",
    # Apache
    "apache 2": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license version 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "apache software license 2.0": "Apache-2.0",
    # BSD-3
    "bsd": "BSD-3-Clause",
    "bsd license": "BSD-3-Clause",
    "new bsd": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "modified bsd": "BSD-3-Clause",
    "3-clause bsd": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "bsd 3-clause license": "BSD-3-Clause",
    "bsd 3 clause": "BSD-3-Clause",
    "bsd (3 clause)": "BSD-3-Clause",
    # BSD-2
    "simplified bsd": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "bsd 2 clause": "BSD-2-Clause",
    "bsd 2-clause license": "BSD-2-Clause",
    # ISC
    "isc license": "ISC",
    "isc license (iscl)": "ISC",
    # Python / PSF
    "python software foundation": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    "psf license": "PSF-2.0",
    "psf": "PSF-2.0",
    "psfl": "PSF-2.0",
    # MPL
    "mpl 2.0": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    # Unlicense / CC0
    "the unlicense": "Unlicense",
    "cc0 1.0 universal": "CC0-1.0",
    # GPL (denied)
    "gpl": "GPL-2.0",
    "gpl v2": "GPL-2.0",
    "gpl v3": "GPL-3.0",
    "gnu gpl v2": "GPL-2.0",
    "gnu gpl v3": "GPL-3.0",
    "gnu general public license v2 or later (gplv2+)": "GPL-2.0-or-later",
    "gnu general public license v3 or later (gplv3+)": "GPL-3.0-or-later",
    # LGPL (denied)
    "lgpl": "LGPL-2.1",
    "lgpl v2": "LGPL-2.0",
    "lgpl v3": "LGPL-3.0",
    "gnu lgpl v2": "LGPL-2.0",
    "gnu lgpl v3": "LGPL-3.0",
    "gnu lesser general public license v2 or later (lgplv2+)": "LGPL-2.0",
    "gnu lesser general public license v3 or later (lgplv3+)": "LGPL-3.0",
    # AGPL (denied)
    "agpl v3": "AGPL-3.0",
    "gnu affero general public license v3 or later (agplv3+)": "AGPL-3.0-or-later",
}

# Ordered keyword patterns for identifying full license texts.
# Earlier entries take priority — keep more specific patterns first.
_FULLTEXT_KEYWORDS: list[tuple[str, str]] = [
    ("gnu lesser general public license", "LGPL-2.1"),
    ("gnu affero general public license", "AGPL-3.0"),
    ("gnu general public license", "GPL-2.0"),
    ("mozilla public license", "MPL-2.0"),
    ("permission is hereby granted, free of charge", "MIT"),
    ("apache license", "Apache-2.0"),
    ("redistribution and use in source and binary forms", "BSD-3-Clause"),
]


def _normalize_license(raw: str) -> str:
    stripped = raw.strip()
    if "\n" not in stripped:
        return _LICENSE_ALIASES.get(stripped.lower(), stripped)
    # Multi-line: try first non-empty line as a short identifier
    first_line = next((l.strip() for l in stripped.splitlines() if l.strip()), stripped)
    result = _LICENSE_ALIASES.get(first_line.lower())
    if result:
        return result
    # Fall back to keyword scan over the full text
    lower = stripped.lower()
    for keyword, spdx in _FULLTEXT_KEYWORDS:
        if keyword in lower:
            return spdx
    return first_line


def _locked_packages(lock_path: Path) -> set[str]:
    """Return normalised package names present in a requirements.lock file."""
    result: set[str] = set()
    if not lock_path.is_file():
        return result
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        m = _LOCK_PKG.match(line.strip())
        if m:
            result.add(m.group(1).lower().replace("-", "_"))
    return result


def validate_licenses(policy: dict, lock_file: Path | None = None) -> list[str]:
    allowed = {_normalize_license(l) for l in policy["allowed"]}
    denied = {_normalize_license(l) for l in policy["denied"]}
    unknown_action = policy.get("unknown_action", "block")
    exceptions_data = _load("dependency-risk-exceptions.json")
    exception_packages = {e["package"] for e in exceptions_data.get("exceptions", [])}

    if lock_file is None:
        lock_file = ROOT / "requirements.lock"
    lock_exists = lock_file.is_file()
    locked = _locked_packages(lock_file)

    failures: list[str] = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"] or ""
        if lock_exists and name.lower().replace("-", "_") not in locked:
            continue
        raw_license = dist.metadata.get("License") or dist.metadata.get("License-Expression") or "Unknown"
        lic = _normalize_license(raw_license)

        if lic in denied:
            if name.lower() not in exception_packages:
                failures.append(f"{name}: denied license '{lic}'")
        elif lic not in allowed:
            if unknown_action == "block" and name.lower() not in exception_packages:
                failures.append(f"{name}: unknown license '{lic}' (block policy)")
    return failures


def validate_direct_dependency_registry(registry: dict, req_file: Path | None = None) -> list[str]:
    if req_file is None:
        req_file = ROOT / "requirements.txt"
    if not req_file.is_file():
        return [f"{req_file} not found"]

    registered = {entry["package"].lower() for entry in registry.get("registry", [])}
    failures: list[str] = []
    for line in req_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pkg = line.split(">=")[0].split("<=")[0].split("==")[0].split("!=")[0].split("<")[0].split(">")[0].strip()
        if pkg.lower() not in registered:
            failures.append(f"requirements.txt entry '{pkg}' missing from direct-dependency-owners.json")
    return failures


def validate_cve_exceptions(exceptions_data: dict) -> list[str]:
    today = date.today()
    failures: list[str] = []
    required_fields = {"id", "package", "owner", "reason", "expires", "accepted_risk"}
    for exc in exceptions_data.get("exceptions", []):
        missing = required_fields - set(exc.keys())
        if missing:
            failures.append(f"CVE exception missing fields {sorted(missing)}: {exc.get('id', '?')}")
            continue
        try:
            expires = date.fromisoformat(exc["expires"])
        except ValueError:
            failures.append(f"CVE exception '{exc['id']}': invalid expires date '{exc['expires']}'")
            continue
        if expires < today:
            failures.append(
                f"CVE exception '{exc['id']}' for '{exc['package']}' expired on {exc['expires']} (owner: {exc['owner']})"
            )
    return failures


def main() -> None:
    policy = _load("dependency-license-policy.json")
    registry = _load("direct-dependency-owners.json")
    exceptions_data = _load("dependency-risk-exceptions.json")

    failures: list[str] = []
    failures.extend(validate_direct_dependency_registry(registry))
    failures.extend(validate_cve_exceptions(exceptions_data))
    failures.extend(validate_licenses(policy))

    if failures:
        raise SystemExit("Dependency policy validation failed:\n- " + "\n- ".join(failures))
    print("Dependency policy validation passed.")


if __name__ == "__main__":
    main()
