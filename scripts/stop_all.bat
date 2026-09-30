@echo off
setlocal EnableDelayedExpansion

:: ===========================================================================
::  Stop every process belonging to the QA Assistant.
::
::  Kills, in order:
::    1. the launcher PIDs recorded in .run\api.pid and .run\web.pid
::    2. any remaining listener on the API port (8000) and web port (3000)
::       -- this catches orphaned --reload children and processes started in
::          an earlier session that never wrote a PID file
::
::  Each kill uses taskkill /T so child processes go with the parent.
::  Pass --quiet to suppress output (used by start_all.bat).
:: ===========================================================================

set "PROJECT_ROOT=%~dp0.."
set "RUN_DIR=%PROJECT_ROOT%\.run"

set "API_PORT=8000"
set "WEB_PORT=3000"

set "QUIET="
if /i "%~1"=="--quiet" set "QUIET=1"

if not defined QUIET (
    echo ============================================================
    echo   QA Assistant - stopping services
    echo ============================================================
    echo.
)

:: --- 1. recorded launcher PIDs --------------------------------------------
for %%F in (api.pid web.pid) do (
    if exist "%RUN_DIR%\%%F" (
        set "TARGET_PID="
        set /p TARGET_PID=<"%RUN_DIR%\%%F"
        if defined TARGET_PID (
            taskkill /PID !TARGET_PID! /T /F >nul 2>&1
            if not errorlevel 1 if not defined QUIET echo   stopped %%F process !TARGET_PID!
        )
        del /q "%RUN_DIR%\%%F" >nul 2>&1
    )
)

:: --- 2. anything still listening on the project ports ---------------------
:: Get-NetTCPConnection prints one owning PID per line here, which is all the
:: batch loop needs. (netstat + findstr is not usable for this: its lines are
:: column-aligned and the regex anchoring is fragile.)
for %%P in (%API_PORT% %WEB_PORT%) do (
    for /f "usebackq delims=" %%O in (`powershell -NoProfile -Command ^
        "try { Get-NetTCPConnection -LocalPort %%P -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess } catch { exit 0 }"`) do (

        set "OWNER=%%O"
        rem Confirm the PID is still alive before killing it.
        powershell -NoProfile -Command "exit [int](-not (Get-Process -Id !OWNER! -ErrorAction SilentlyContinue))" >nul 2>&1
        if not errorlevel 1 (
            taskkill /PID !OWNER! /T /F >nul 2>&1
            if not errorlevel 1 if not defined QUIET echo   stopped listener on port %%P ^(PID !OWNER!^)
        )
    )
)

if not defined QUIET (
    echo.
    echo Done. Nothing should be listening on ports %API_PORT% or %WEB_PORT%.
    echo.
)

exit /b 0
