$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv/Scripts/python.exe"
if (!(Test-Path $python)) { throw "Create .venv and install requirements.txt first." }
& $python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)"
if ($LASTEXITCODE -ne 0) { throw "This project requires Python 3.13. Create .venv with py -3.13 -m venv .venv." }
& $python -m app.main
exit $LASTEXITCODE
