param(
    [Parameter(Mandatory = $true)]
    [string]$Task,

    [ValidateSet("Baseline", "Release-ready", "Audit-ready")]
    [string]$TargetState = "Baseline",

    [string]$Scope = "Full repository",

    [ValidateSet("P0", "P0+P1", "All")]
    [string]$BlockingThreshold = "P0",

    [string]$OutputPath = "prompts/current-task.md"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$priority = @{
    "security-architect"      = 1
    "ai-compliance-owner"     = 2
    "release-manager"         = 3
    "data-protection-officer" = 4
    "model-privacy-owner"     = 5
    "agent-security-owner"    = 6
    "license-owner"           = 7
    "audit-owner"             = 8
    "human-reviewer"          = 9
    "code-reviewer"           = 10
    "product-owner"           = 11
    "maintainer"              = 12
}

$catalog = @(
    @{
        id = "product-owner"
        goal = "Specify use case, product goal, and scope consistently."
        output = "Requirements-gate assessment with clear task objective."
        keywords = @("use case", "requirements", "product goal", "scope")
        scopeHints = @("docs/en/architecture")
    },
    @{
        id = "ai-compliance-owner"
        goal = "Validate AI Act role, risk class, and governance evidence."
        output = "AI-risk-gate assessment with evidence-based findings."
        keywords = @("ai act", "compliance", "governance", "risk class")
        scopeHints = @("docs/en/ai-act", "docs/en/ai-governance")
    },
    @{
        id = "security-architect"
        goal = "Assess threat model, DevSecOps controls, and enforcement mechanisms."
        output = "Security-gate assessment including P0 security blockers."
        keywords = @("security", "threat", "devsecops", "owasp", "rego", "policy", "workflow")
        scopeHints = @("docs/en/security", "policies", ".github/workflows", "scripts", "bom")
    },
    @{
        id = "data-protection-officer"
        goal = "Assess GDPR, DPIA, PII risks, and privacy controls."
        output = "Privacy-gate assessment for personal data controls."
        keywords = @("gdpr", "dpia", "pii", "data subject", "privacy", "tom")
        scopeHints = @("docs/en/privacy")
    },
    @{
        id = "model-privacy-owner"
        goal = "Enforce model routing and local/EU/cloud privacy strategy."
        output = "Model-privacy-gate assessment for model routing paths."
        keywords = @("model routing", "provider", "eu hosted", "local model", "inference route")
        scopeHints = @("docs/en/models")
    },
    @{
        id = "agent-security-owner"
        goal = "Validate agent-to-agent security, zero trust, and tool permissions."
        output = "Agent-security-gate assessment for agent communications."
        keywords = @("agent communication", "zero trust", "tool rights", "signed messages", "agent")
        scopeHints = @("docs/en/agents", "policies/rego")
    },
    @{
        id = "license-owner"
        goal = "Validate OSS, model, dataset, and prompt licensing."
        output = "License-gate assessment including BOM/license blockers."
        keywords = @("license", "oss", "dataset license", "prompt license")
        scopeHints = @("docs/en/licenses", "bom")
    },
    @{
        id = "human-reviewer"
        goal = "Ensure human oversight for critical decisions."
        output = "Human-approval-gate assessment for critical decisions."
        keywords = @("critical decision", "human approval", "escalation", "oversight")
        scopeHints = @("docs/en/agents", "docs/en/ai-governance")
    },
    @{
        id = "code-reviewer"
        goal = "Evaluate readability, maintainability, complexity, and review quality."
        output = "Code-review-gate assessment with concrete maintainability findings."
        keywords = @("code review", "readability", "maintainability", "complexity", "review quality")
        scopeHints = @("scripts", "tests", ".github/workflows")
    },
    @{
        id = "release-manager"
        goal = "Assess release approval, signing, and artifact completeness."
        output = "Release-gate assessment with merge/release status."
        keywords = @("release", "signing", "attestation", "artifact")
        scopeHints = @("bom", ".github/workflows", "docs/en/audit")
    },
    @{
        id = "audit-owner"
        goal = "Assess audit trail, evidence integrity, and archiving controls."
        output = "Audit-gate assessment for auditability and retention."
        keywords = @("audit trail", "evidence", "archiving", "retention")
        scopeHints = @("docs/en/audit", "bom", "scripts")
    },
    @{
        id = "maintainer"
        goal = "Ensure implementation quality, tests, and CI reliability."
        output = "Quality-gate assessment for implementation and testing."
        keywords = @("implementation", "bugfix", "tests", "refactor", "ci", "script")
        scopeHints = @("scripts", "policies", ".github/workflows")
    }
)

function Contains-Match {
    param(
        [string]$Text,
        [string[]]$Tokens
    )

    foreach ($token in $Tokens) {
        if ($Text.Contains($token.ToLowerInvariant())) {
            return $true
        }
    }
    return $false
}

function Add-Role {
    param(
        [hashtable]$Role,
        [System.Collections.Generic.HashSet[string]]$SelectedIds
    )
    [void]$SelectedIds.Add($Role.id)
}

$combined = "$Task $Scope".ToLowerInvariant()
$selectedRoleIds = [System.Collections.Generic.HashSet[string]]::new()

foreach ($role in $catalog) {
    if (Contains-Match -Text $combined -Tokens $role.keywords) {
        Add-Role -Role $role -SelectedIds $selectedRoleIds
        continue
    }
    if (Contains-Match -Text $Scope.ToLowerInvariant() -Tokens $role.scopeHints) {
        Add-Role -Role $role -SelectedIds $selectedRoleIds
    }
}

switch ($TargetState) {
    "Baseline" {
        [void]$selectedRoleIds.Add("maintainer")
        [void]$selectedRoleIds.Add("code-reviewer")
    }
    "Release-ready" {
        [void]$selectedRoleIds.Add("security-architect")
        [void]$selectedRoleIds.Add("ai-compliance-owner")
        [void]$selectedRoleIds.Add("release-manager")
        [void]$selectedRoleIds.Add("code-reviewer")
        [void]$selectedRoleIds.Add("maintainer")
    }
    "Audit-ready" {
        [void]$selectedRoleIds.Add("audit-owner")
        [void]$selectedRoleIds.Add("ai-compliance-owner")
        [void]$selectedRoleIds.Add("security-architect")
        [void]$selectedRoleIds.Add("code-reviewer")
        [void]$selectedRoleIds.Add("maintainer")
    }
}

if ($selectedRoleIds.Count -eq 0) {
    [void]$selectedRoleIds.Add("maintainer")
}

$selectedRoles = $catalog |
    Where-Object { $selectedRoleIds.Contains($_.id) } |
    Sort-Object { $priority[$_.id] }

$roleLines = New-Object System.Collections.Generic.List[string]
$i = 1
foreach ($role in $selectedRoles) {
    $line = "$i. $($role.id) - Goal: $($role.goal) - Output: $($role.output)"
    $roleLines.Add($line) | Out-Null
    $i++
}

$conflictOrder = ($selectedRoles | ForEach-Object { $_.id }) -join " > "

$report = @(
    "Task: $Task"
    ""
    "Target State: $TargetState"
    "Scope: $Scope"
    "Blocking Threshold: $BlockingThreshold"
    ""
    "Specialist Plan:"
)
$report += $roleLines
$report += @(
    ""
    "Gate Rule:"
    "- Merge is ALLOWED only if all required roles report no blocking findings."
    "- Conflict resolver: $conflictOrder."
    ""
    "Dynamic Expansion:"
    "- Trigger detected: <yes/no>"
    "- New role: <role>"
    "- Reason: <evidence-based reason>"
    "- Status: <added during execution>"
    ""
    "Final Output:"
    "- One consolidated report with one section per role plus a final global decision."
)

$targetDir = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($targetDir)) {
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
}

Set-Content -Path $OutputPath -Value ($report -join [Environment]::NewLine) -Encoding UTF8

Write-Output "Created $OutputPath with $($selectedRoles.Count) role(s)."
Write-Output "Role order: $conflictOrder"
