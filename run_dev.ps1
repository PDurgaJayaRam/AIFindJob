# PowerShell script to run both frontend and backend
# Usage: .\run_dev.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "JOBFinder SaaS - Starting Development" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "Please edit .env with your API keys before continuing." -ForegroundColor Red
    pause
    exit 1
}

# Create data directory if needed
if (-not (Test-Path "data")) {
    New-Item -ItemType Directory -Path "data" | Out-Null
}

# Start backend in background
Write-Host "Starting FastAPI backend on port 8000..." -ForegroundColor Green
Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info" -WindowStyle Normal

# Wait for backend to start
Start-Sleep -Seconds 3

# Start frontend
Write-Host "Starting React frontend on port 3000..." -ForegroundColor Green
Set-Location "frontend-3d"
Start-Process -FilePath "npm" -ArgumentList "run", "dev" -WindowStyle Normal

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Both servers starting..." -ForegroundColor Cyan
Write-Host "Backend: http://localhost:8000" -ForegroundColor Green
Write-Host "Frontend: http://localhost:3000" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

Set-Location ".."
pause