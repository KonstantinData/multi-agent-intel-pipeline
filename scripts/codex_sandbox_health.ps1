param(
    [int]$TimeoutSeconds = 10,
    [switch]$RunPytestSmoke,
    [string]$ObservedSandboxError = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param(
        [string]$Name,
        [ValidateSet("PASS", "WARN", "FAIL", "INFO")]
        [string]$Status,
        [string]$Detail
    )

    $results.Add([pscustomobject]@{
        Check = $Name
        Status = $Status
        Detail = $Detail
    }) | Out-Null
}

function Invoke-HealthCommand {
    param(
        [string]$Name,
        [scriptblock]$ScriptBlock,
        [int]$Timeout = $TimeoutSeconds,
        [switch]$AllowFailure
    )

    $job = Start-Job -ScriptBlock $ScriptBlock
    try {
        $completed = Wait-Job -Job $job -Timeout $Timeout
        if (-not $completed) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
            Add-Result $Name "FAIL" "Timed out after $Timeout second(s)."
            return
        }

        $output = Receive-Job -Job $job -ErrorAction Stop 2>&1
        if ($job.State -eq "Failed") {
            $detail = ($output | Out-String).Trim()
            if ([string]::IsNullOrWhiteSpace($detail)) {
                $detail = "Command failed without output."
            }
            Add-Result $Name ($(if ($AllowFailure) { "WARN" } else { "FAIL" })) $detail
            return
        }

        $text = ($output | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($text)) {
            $text = "OK"
        }
        Add-Result $Name "PASS" $text
    }
    catch {
        Add-Result $Name ($(if ($AllowFailure) { "WARN" } else { "FAIL" })) $_.Exception.Message
    }
    finally {
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
}

function Get-CommandPath {
    param([string]$CommandName)

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return ""
    }
    return $command.Source
}

Write-Host "Codex sandbox healthcheck"
Write-Host "Repo: $repoRoot"
Write-Host "Time: $((Get-Date).ToString("s"))"
Write-Host ""

Add-Result "Repository root" "INFO" $repoRoot
Add-Result "PowerShell host" "INFO" "$($PSVersionTable.PSEdition) $($PSVersionTable.PSVersion) via $((Get-Process -Id $PID).Path)"
Add-Result "Current user" "INFO" "$env:USERDOMAIN\$env:USERNAME"

if (-not [string]::IsNullOrWhiteSpace($ObservedSandboxError)) {
    Add-Result "Observed Codex sandbox error" "FAIL" $ObservedSandboxError
}

$profilePaths = @(
    $PROFILE.AllUsersAllHosts,
    $PROFILE.AllUsersCurrentHost,
    $PROFILE.CurrentUserAllHosts,
    $PROFILE.CurrentUserCurrentHost
) | Sort-Object -Unique

$existingProfiles = @($profilePaths | Where-Object { Test-Path $_ })
if ($existingProfiles.Count -gt 0) {
    Add-Result "PowerShell profiles" "WARN" ("Existing profiles can slow or block interactive shells: " + ($existingProfiles -join "; "))
}
else {
    Add-Result "PowerShell profiles" "PASS" "No profile files found for this host."
}

$pwshPath = Get-CommandPath "pwsh"
if ([string]::IsNullOrWhiteSpace($pwshPath)) {
    Add-Result "pwsh on PATH" "WARN" "PowerShell 7 'pwsh' is not on PATH."
}
else {
    Add-Result "pwsh on PATH" "PASS" $pwshPath
    Invoke-HealthCommand "pwsh -NoProfile child process" {
        pwsh -NoProfile -NonInteractive -Command '$PSVersionTable.PSVersion.ToString()'
    }
}

Invoke-HealthCommand "Windows PowerShell child process" {
    powershell -NoProfile -NonInteractive -Command '$PSVersionTable.PSVersion.ToString()'
}

$healthDir = Join-Path $repoRoot ".codex\sandbox-health"
Invoke-HealthCommand "Workspace write/delete" {
    New-Item -ItemType Directory -Force -Path "$using:healthDir" | Out-Null
    $probe = Join-Path "$using:healthDir" "write-probe.txt"
    Set-Content -LiteralPath $probe -Value "ok" -Encoding ASCII
    $value = Get-Content -LiteralPath $probe -Raw
    Remove-Item -LiteralPath $probe -Force
    "write probe: $($value.Trim())"
}

Invoke-HealthCommand "git version" {
    git --version
}

Invoke-HealthCommand "git status short" {
    Set-Location "$using:repoRoot"
    $status = git status --short
    if ($LASTEXITCODE -ne 0) {
        throw "git status failed with exit code $LASTEXITCODE"
    }
    if ($status) {
        $status
    }
    else {
        "clean"
    }
}

Invoke-HealthCommand "git signing config" {
    Set-Location "$using:repoRoot"
    $program = git config --get gpg.program
    $key = git config --get user.signingkey
    $enabled = git config --get commit.gpgsign
    "gpg.program=$program; user.signingkey=$key; commit.gpgsign=$enabled"
} -AllowFailure

$configuredGpgProgram = ""
try {
    Push-Location $repoRoot
    $configuredGpgProgram = (git config --get gpg.program 2>$null)
}
finally {
    Pop-Location
}

$gpgCommand = "gpg"
if (-not [string]::IsNullOrWhiteSpace($configuredGpgProgram) -and (Test-Path $configuredGpgProgram)) {
    $gpgCommand = $configuredGpgProgram
}

Invoke-HealthCommand "gpg availability" {
    & "$using:gpgCommand" --version | Select-Object -First 1
} -AllowFailure

Invoke-HealthCommand "repo signing key" {
    & "$using:gpgCommand" --list-secret-keys --keyid-format=long 3EB5B5E8705BDA15
} -AllowFailure

Invoke-HealthCommand "python version" {
    python --version
}

Invoke-HealthCommand "python executable" {
    python -c "import sys; print(sys.executable)"
}

Invoke-HealthCommand "pytest version" {
    pytest --version
} -AllowFailure

if ($RunPytestSmoke) {
    Invoke-HealthCommand "architecture pytest smoke" {
        Set-Location "$using:repoRoot"
        pytest -q tests/architecture/test_runtime_step1.py
    } -Timeout ([Math]::Max($TimeoutSeconds, 60)) -AllowFailure
}

if (Test-Path (Join-Path $repoRoot "ui")) {
    Invoke-HealthCommand "node version" {
        node --version
    } -AllowFailure

    Invoke-HealthCommand "npm version" {
        npm --version
    } -AllowFailure
}

$defenderCandidates = @(
    ".git",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "artifacts",
    "ui\node_modules"
)

$existingDefenderCandidates = @($defenderCandidates |
    ForEach-Object { Join-Path $repoRoot $_ } |
    Where-Object { Test-Path $_ })

if ($existingDefenderCandidates.Count -gt 0) {
    Add-Result "Defender exclusion candidates" "INFO" ($existingDefenderCandidates -join "; ")
}

Write-Host "Results"
$results | Format-Table -AutoSize -Wrap

$failed = @($results | Where-Object { $_.Status -eq "FAIL" })
$warnings = @($results | Where-Object { $_.Status -eq "WARN" })

Write-Host ""
Write-Host "Summary: $($failed.Count) failed, $($warnings.Count) warning(s)."

if ($failed.Count -gt 0) {
    exit 1
}
