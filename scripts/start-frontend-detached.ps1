$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDirectory = Join-Path $projectRoot ".codex\dev-logs"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logDirectory "frontend-$timestamp.log"

$packageManager = $env:BIDRADAR_PACKAGE_MANAGER
if (-not $packageManager) {
    $command = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $command) {
        $command = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    }
    if (-not $command) {
        throw "npm.cmd or pnpm.cmd not found. Set BIDRADAR_PACKAGE_MANAGER."
    }
    $packageManager = $command.Source
}

Set-Location $projectRoot
& $packageManager run dev:web *> $logPath
