@echo off
:: Start both FastAPI and React Vite servers on Windows

set PROJECT_ROOT=%~dp0..

echo Starting FastAPI server...
start "QA-Backend" cmd /k "cd /d %PROJECT_ROOT% && uvicorn src.presentation.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000"

:: Wait for the API to be ready
echo Waiting for API to be ready...
set /a count=0
:wait_loop
if %count% geq 30 (
    echo API failed to start within 30 seconds.
    exit /b 1
)
timeout /t 1 /nobreak >nul
curl -s http://localhost:8000/api/health >nul 2>&1
if %errorlevel% equ 0 (
    echo API is ready!
    goto start_frontend
)
set /a count+=1
goto wait_loop

:start_frontend
echo Starting React Vite frontend...
start "QA-Frontend" cmd /k "cd /d %PROJECT_ROOT%\src\presentation\react && npm run dev"

echo.
echo Servers started!
echo API:       http://localhost:8000
echo Frontend:  http://localhost:3000
echo API Docs:  http://localhost:8000/docs
