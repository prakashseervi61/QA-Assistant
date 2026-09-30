@echo off
setlocal EnableDelayedExpansion

:: ===========================================================================
::  Start the QA Assistant (FastAPI + Vite) in the background.
::
::  Both servers are launched as hidden processes, so no terminal windows are
::  left on the desktop. This launcher waits until they are actually ready,
::  opens the browser, writes PID files for stop_all.bat, then exits.
::
::  Run start_all.bat to start, stop_all.bat to stop.
:: ===========================================================================

set "PROJECT_ROOT=%~dp0.."
set "REACT_DIR=%PROJECT_ROOT%\src\presentation\react"
set "RUN_DIR=%PROJECT_ROOT%\.run"
set "LOG_DIR=%RUN_DIR%\logs"

set "API_PORT=8000"
set "WEB_PORT=3000"
set "URL=http://localhost:%WEB_PORT%"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

echo ============================================================
echo   QA Assistant - starting services
echo ============================================================
echo.

:: --- stop anything left over from a previous run -----------------------
call "%~dp0stop_all.bat" --quiet
echo.

:: --- backend ---------------------------------------------------------------
:: No --reload here on purpose: it re-imports the whole app in a child
:: process, roughly doubling startup, and leaves a grandchild that the PID
:: file does not track. Stop and start to pick up backend code changes.
echo Starting API  (port %API_PORT%)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Remove-Item '%RUN_DIR%\api.pid' -Force -ErrorAction SilentlyContinue;" ^
  "Remove-Item '%RUN_DIR%\web.pid' -Force -ErrorAction SilentlyContinue;" ^
  "$uvicornArgs = @('src.presentation.api.app:create_app','--factory','--host','0.0.0.0','--port','%API_PORT%');" ^
  "$uvicorn = Get-Command uvicorn -ErrorAction SilentlyContinue;" ^
  "if ($uvicorn) { $exe = $uvicorn.Source; $argList = $uvicornArgs }" ^
  "else { $exe = (Get-Command python -ErrorAction Stop).Source; $argList = @('-m','uvicorn') + $uvicornArgs };" ^
  "$p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory '%PROJECT_ROOT%' -WindowStyle Hidden -PassThru -RedirectStandardOutput '%LOG_DIR%\api.out.log' -RedirectStandardError '%LOG_DIR%\api.err.log';" ^
  "Set-Content -Path '%RUN_DIR%\api.pid' -Value $p.Id -NoNewline" >nul 2>&1

if not exist "%RUN_DIR%\api.pid" (
    echo [X] Failed to launch the API. See "%LOG_DIR%\api.err.log"
    exit /b 1
)

:: --- frontend (started immediately, not gated on the API) ----------------
echo Starting web UI  (port %WEB_PORT%)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue);" ^
  "if (-not $npm) { $npm = (Get-Command npm -ErrorAction Stop) };" ^
  "$p = Start-Process -FilePath $npm.Source -ArgumentList @('run','dev','--','--host','127.0.0.1','--port','%WEB_PORT%') -WorkingDirectory '%REACT_DIR%' -WindowStyle Hidden -PassThru -RedirectStandardOutput '%LOG_DIR%\web.out.log' -RedirectStandardError '%LOG_DIR%\web.err.log';" ^
  "Set-Content -Path '%RUN_DIR%\web.pid' -Value $p.Id -NoNewline" >nul 2>&1

if not exist "%RUN_DIR%\web.pid" (
    echo [X] Failed to launch the web UI. See "%LOG_DIR%\web.err.log"
    exit /b 1
)

:: --- wait for the web UI, then open the browser --------------------------
:: Vite comes up in a second or two, so this is the gate that matters for
:: "how fast does the browser open". The API is reported on separately below.
call :waiturl "%URL%" 45 WEB_OK
if not defined WEB_OK (
    echo [!] The web UI did not answer in 45s. See "%LOG_DIR%\web.err.log"
)

:: --- open the browser as soon as the page is servable ---------------------
start "" "%URL%"

:: --- report API health (informational, never blocks the browser) ----------
call :waiturl "http://localhost:%API_PORT%/api/health" 90 API_OK

echo.
echo ============================================================
echo   Running in the background - no terminals left open.
echo.
if defined WEB_OK   echo   Web UI  ready  -  %URL%
if defined API_OK   echo   API      ready  -  http://localhost:%API_PORT%
if not defined API_OK echo   [!] API still starting - see %LOG_DIR%\api.err.log
echo.
echo   API Docs  http://localhost:%API_PORT%/docs
echo   Logs      %LOG_DIR%
echo.
echo   Stop with scripts\stop_all.bat
echo ============================================================

powershell -NoProfile -Command "Start-Sleep -Seconds 3" >nul 2>&1
exit /b 0


:: ===========================================================================
::  :waiturl <url> <timeout-seconds> <flag-name>
::
::  Polls <url> until it answers or the budget runs out, then sets <flag-name>.
::  The polling loop lives inside a single PowerShell process: doing it in batch
::  would spawn two processes per second, and `timeout` is shadowed by the GNU
::  coreutils build in Git Bash, which silently breaks the sleep.
:: ===========================================================================
:waiturl
set "%~3="
powershell -NoProfile -Command ^
  "$deadline = (Get-Date).AddSeconds(%~2);" ^
  "while ((Get-Date) -lt $deadline) {" ^
  "  try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%~1' | Out-Null; exit 0 }" ^
  "  catch { Start-Sleep -Milliseconds 400 }" ^
  "}" ^
  "exit 1" >nul 2>&1
if not errorlevel 1 set "%~3=1"
goto :eof
