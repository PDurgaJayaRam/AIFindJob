@echo off
REM JOBFinder - Run both frontend and backend
REM Usage: run_dev.bat

echo ========================================
echo JOBFinder SaaS - Starting Development Server
echo ========================================

REM Check if .env exists
if not exist ".env" (
    echo Creating .env from .env.example...
    copy .env.example .env
    echo Please edit .env with your API keys before continuing.
    pause
    exit /b 1
)

REM Create data directory if needed
if not exist "data" mkdir data

REM Start backend in background
echo Starting FastAPI backend on port 8000...
start "Backend" cmd /c "python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info"

REM Wait for backend to start
timeout /t 3 /nobreak >nul

REM Start frontend
echo Starting React frontend on port 3000...
cd frontend-3d
start "Frontend" cmd /c "npm run dev"

echo.
echo ========================================
echo Both servers starting...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo ========================================
echo.
pause