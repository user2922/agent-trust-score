# The demo, paced for a screen recording. PowerShell.
#
#   .\scripts\demo.ps1           # paced, pauses between beats
#   .\scripts\demo.ps1 -Fast     # no pauses, for a rehearsal
#
# Runs entirely against locally generated fixtures with --no-llm: no API key, no
# network, no cost. Nothing is pre-recorded -- every number is computed live.
#
# Depends on nothing being on PATH. It calls the project's own interpreter
# directly, so a fresh terminal works.

param([switch]$Fast)

# NOT "Stop": redirecting a native command's stderr in PowerShell wraps each
# line in an ErrorRecord, so the deliberate "below --min-grade" message at the
# end would abort the script instead of being the point of the beat.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$pause = if ($Fast) { 0 } else { 2.5 }
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "Project environment missing. Run this first:" -ForegroundColor Red
    Write-Host "  uv sync --extra dev"
    exit 1
}

$demo = ".demo"
function Beat($text) {
    Write-Host ""
    Write-Host "-- $text" -ForegroundColor DarkGray
    Write-Host ""
    Start-Sleep -Seconds $pause
}
function Audit { & $py -m agent_trust @args }

# ── setup, silent ───────────────────────────────────────────────────────────
if (Test-Path $demo) { Remove-Item $demo -Recurse -Force }
& $py scripts\build_fixtures.py $demo | Out-Null

Clear-Host
Write-Host "Agent Trust Score" -ForegroundColor White -NoNewline
Write-Host " - how safely can an agent work in this repository?"
Start-Sleep -Seconds $pause

# ── 1 · the repository an agent should not touch ────────────────────────────
Beat "A repository an agent should not touch"
Audit "$demo\ugly-repo" --no-llm --no-cache --format md --format json --format html `
      --out "$demo\ugly-out" | Select-Object -First 20

# ── 2 · it found a credential, and never printed it ─────────────────────────
Beat "It found a committed credential - and never printed it"
Select-String -Path "$demo\ugly-out\report.md" -Pattern '^\*\*`BR-01`', '^- `.*AKIA' |
    Select-Object -First 4 | ForEach-Object { $_.Line }

# Assembled from fragments so this file carries no literal the detector matches.
$planted = "AKIA" + "Q7RSTUVWX1234567"
$artifacts = @(Get-ChildItem "$demo\ugly-out" -File)
$leaks = @($artifacts | Where-Object { (Get-Content $_.FullName -Raw) -like "*$planted*" })

Write-Host ""
Write-Host "The planted key is 20 characters. Grep all $($artifacts.Count) artifacts for it:" -ForegroundColor DarkGray
if ($leaks.Count -eq 0) {
    Write-Host "  0 leaks" -ForegroundColor Green -NoNewline
    Write-Host " - markdown, JSON and HTML. Redaction happens at capture,"
    Write-Host "  not at render, so no code path downstream can leak it."
} else {
    Write-Host "  $($leaks.Count) LEAK(S)" -ForegroundColor Red
}

# ── 3 · what good looks like ────────────────────────────────────────────────
Beat "The same tool on a well-prepared repository"
Audit "$demo\clean-repo" --no-llm --no-cache --out "$demo\clean-out" | Select-Object -First 16

# ── 4 · it grades itself ────────────────────────────────────────────────────
Beat "And on itself - the remaining findings are real, not hidden"
Audit . --no-llm --no-cache --out "$demo\self-out" | Select-Object -First 16

# ── 5 · the CI gate ─────────────────────────────────────────────────────────
Beat "Usable as a CI gate"
Write-Host "PS> agent-trust . --min-grade A --quiet"
Audit . --no-llm --quiet --no-cache --min-grade A --out "$demo\self-out" | Out-Null
Write-Host "exit $LASTEXITCODE   (0 - passed the floor)"
Write-Host ""
Write-Host "PS> agent-trust .demo\ugly-repo --min-grade B --quiet"
Audit "$demo\ugly-repo" --no-llm --quiet --no-cache --min-grade B --out "$demo\ugly-out" | Out-Null
Write-Host "exit $LASTEXITCODE   (2 - below the floor, the build fails)"

Write-Host ""
Write-Host "Reports in $demo\*\report.html     MCP server: python -m agent_trust.mcp_server" -ForegroundColor DarkGray
Write-Host ""

exit 0
