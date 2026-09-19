@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Install uv first: https://docs.astral.sh/uv/getting-started/installation/
  pause
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 22 or newer, then run this file again.
  pause
  exit /b 1
)
uv run --directory backend python ../scripts/run_local.py %*
if errorlevel 1 (
  echo Local services stopped or could not start. See the message above.
  pause
)
endlocal
