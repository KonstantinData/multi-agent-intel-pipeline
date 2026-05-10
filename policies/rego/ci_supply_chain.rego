package ci_supply_chain

import rego.v1

# Deny pull_request_target trigger
deny contains msg if {
    input.on.pull_request_target
    msg := sprintf("workflow '%s': pull_request_target trigger is forbidden", [input.name])
}

# Deny write-all permissions
deny contains msg if {
    input.permissions == "write-all"
    msg := sprintf("workflow '%s': write-all permissions are forbidden", [input.name])
}

# Deny empty permissions block {}
deny contains msg if {
    input.permissions == {}
    msg := sprintf("workflow '%s': empty permissions block is forbidden", [input.name])
}

# Deny unnecessary write permissions outside release/attestation jobs
deny contains msg if {
    some job_name, job in input.jobs
    not _is_release_job(job_name)
    some perm, level in job.permissions
    level == "write"
    not _allowed_write_perm(perm)
    msg := sprintf("workflow '%s' job '%s': unexpected write permission '%s'", [input.name, job_name, perm])
}

_is_release_job(name) if {
    regex.match("(release|attest|provenance)", name)
}

_allowed_write_perm(perm) if {
    perm in {"security-events", "id-token", "attestations", "artifact-metadata"}
}

# Deny external actions not pinned to full SHA
deny contains msg if {
    some job_name, job in input.jobs
    some step in job.steps
    ref := step.uses
    ref != null
    not startswith(ref, "./")
    not startswith(ref, "docker://")
    not regex.match("^[^@]+@[0-9a-f]{40}$", ref)
    msg := sprintf("workflow '%s' job '%s': action '%s' must be pinned to full SHA", [input.name, job_name, ref])
}

# Deny docker scanner images not digest-pinned
deny contains msg if {
    some job_name, job in input.jobs
    some step in job.steps
    ref := step.uses
    ref != null
    startswith(ref, "docker://")
    not regex.match("@sha256:[0-9a-f]{64}", ref)
    msg := sprintf("workflow '%s' job '%s': docker image '%s' must be digest-pinned", [input.name, job_name, ref])
}

# Deny optional CodeQL guard (ENABLE_CODEQL variable gate)
deny contains msg if {
    some job_name, job in input.jobs
    regex.match("(?i)codeql", job_name)
    cond := job["if"]
    regex.match("ENABLE_CODEQL", cond)
    msg := sprintf("workflow '%s' job '%s': CodeQL must not be gated on ENABLE_CODEQL variable", [input.name, job_name])
}

# Deny governance docs with placeholder markers
deny contains msg if {
    some path in input.governance_files
    content := input.governance_content[path]
    regex.match("(TODO|REVIEW_REQUIRED|TBD)", content)
    msg := sprintf("governance file '%s' contains placeholder marker", [path])
}
