$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
$python = $env:BIDRADAR_PYTHON
if (-not $python) {
    $venvPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        $python = $venvPython
    } else {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            throw "Python not found. Set BIDRADAR_PYTHON or create backend/.venv."
        }
        $python = $pythonCommand.Source
    }
}
$logDirectory = Join-Path $projectRoot ".codex\dev-logs"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logDirectory "backend-$timestamp.log"

Set-Location $backendRoot
& $python "run.py" *> $logPath
