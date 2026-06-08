# PC fallback: load .env and run one sweep. Wire this into Windows Task Scheduler
# if you'd rather run from your German IP than from GitHub's US runners.
#
# Register an hourly task (run once in PowerShell, adjust the path if you move the folder):
#   schtasks /Create /SC HOURLY /TN "FS1PlateWatcher" /TR `
#     "powershell -NoProfile -ExecutionPolicy Bypass -File `"$PWD\run_local.ps1`""
#
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ".env") {
  Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
      [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
  }
}

& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\monitor.py"
