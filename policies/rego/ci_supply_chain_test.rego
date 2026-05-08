package ci_supply_chain

import rego.v1

# ---------------------------------------------------------------------------
# pull_request_target
# ---------------------------------------------------------------------------

test_deny_pull_request_target if {
	count(deny) > 0 with input as {
		"name": "bad-workflow",
		"on": {"pull_request_target": {}},
		"permissions": {"contents": "read"},
		"jobs": {},
	}
}

test_allow_no_pull_request_target if {
	count(deny) == 0 with input as {
		"name": "good-workflow",
		"permissions": {"contents": "read"},
		"jobs": {},
	}
}

# ---------------------------------------------------------------------------
# write-all permissions
# ---------------------------------------------------------------------------

test_deny_write_all if {
	count(deny) > 0 with input as {
		"name": "bad-workflow",
		"permissions": "write-all",
		"jobs": {},
	}
}

# ---------------------------------------------------------------------------
# SHA pinning for external actions
# ---------------------------------------------------------------------------

test_deny_unpinned_external_action if {
	count(deny) > 0 with input as {
		"name": "bad-workflow",
		"permissions": {"contents": "read"},
		"jobs": {"build": {"steps": [{"uses": "actions/checkout@v4"}]}},
	}
}

test_deny_branch_pinned_action if {
	count(deny) > 0 with input as {
		"name": "bad-workflow",
		"permissions": {"contents": "read"},
		"jobs": {"build": {"steps": [{"uses": "actions/checkout@main"}]}},
	}
}

test_allow_sha_pinned_external_action if {
	count(deny) == 0 with input as {
		"name": "good-workflow",
		"permissions": {"contents": "read"},
		"jobs": {"build": {"steps": [{"uses": "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"}]}},
	}
}

test_allow_local_action if {
	count(deny) == 0 with input as {
		"name": "good-workflow",
		"permissions": {"contents": "read"},
		"jobs": {"build": {"steps": [{"uses": "./local-action"}]}},
	}
}

# ---------------------------------------------------------------------------
# Docker image digest pinning
# ---------------------------------------------------------------------------

test_deny_docker_image_without_digest if {
	count(deny) > 0 with input as {
		"name": "bad-workflow",
		"permissions": {"contents": "read"},
		"jobs": {"scan": {"steps": [{"uses": "docker://anchore/syft:latest"}]}},
	}
}

test_allow_docker_image_with_digest if {
	count(deny) == 0 with input as {
		"name": "good-workflow",
		"permissions": {"contents": "read"},
		"jobs": {"scan": {"steps": [{"uses": "docker://anchore/syft@sha256:d2e42aacd6a3f602e2e94f6ef77b102852f76778a8060272c88d567fb6fedecf"}]}},
	}
}

# ---------------------------------------------------------------------------
# ENABLE_CODEQL guard
# ---------------------------------------------------------------------------

test_deny_codeql_with_enable_guard if {
	count(deny) > 0 with input as {
		"name": "codeql",
		"permissions": {"contents": "read"},
		"jobs": {
			"codeql": {
				"if": "vars.ENABLE_CODEQL == 'true'",
				"steps": [],
			},
		},
	}
}

test_allow_codeql_without_guard if {
	count(deny) == 0 with input as {
		"name": "codeql",
		"permissions": {"contents": "read"},
		"jobs": {"codeql": {"steps": []}},
	}
}

# ---------------------------------------------------------------------------
# Unexpected write permissions outside release jobs
# ---------------------------------------------------------------------------

test_deny_write_permission_in_non_release_job if {
	count(deny) > 0 with input as {
		"name": "bad-workflow",
		"permissions": {"contents": "read"},
		"jobs": {
			"build": {
				"permissions": {"contents": "write"},
				"steps": [],
			},
		},
	}
}

test_allow_security_events_write_in_any_job if {
	msgs := {m | deny[m]; regex.match("security-events", m)} with input as {
		"name": "good-workflow",
		"permissions": {"contents": "read"},
		"jobs": {
			"scan": {
				"permissions": {"security-events": "write"},
				"steps": [],
			},
		},
	}
	count(msgs) == 0
}
