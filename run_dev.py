"""Run both backend and frontend in development mode.

Usage:
    python run_dev.py
    
This starts:
- FastAPI backend on port 8000
- Vite frontend on port 3000
"""
import sys
import subprocess
import time
import signal
import threading
import shutil
from pathlib import Path

def run_backend():
    """Run FastAPI backend."""
    print("[BACKEND] Starting FastAPI on port 8000...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=Path(__file__).parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:
        print(f"[BACKEND] {line.rstrip()}")

def run_frontend():
    """Run Vite frontend."""
    print("[FRONTEND] Starting Vite on port 3000...")
    
    # Find npm in PATH (handles Windows PATHEXT extensions like .cmd, .ps1)
    npm_path = shutil.which("npm")
    if npm_path is None:
        print("[ERROR] npm not found in PATH. Please install Node.js.")
        return
    
    proc = subprocess.Popen(
        [npm_path, "run", "dev"],
        cwd=Path(__file__).parent / "frontend-3d",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:
        print(f"[FRONTEND] {line.rstrip()}")

def main():
    print("=" * 50)
    print("  JOBFinder SaaS - Development Mode")
    print("=" * 50)
    print()
    
    # Create data directory if needed
    Path("data").mkdir(exist_ok=True)
    
    # Start both processes in threads
    backend_thread = threading.Thread(target=run_backend, daemon=True)
    frontend_thread = threading.Thread(target=run_frontend, daemon=True)
    
    backend_thread.start()
    time.sleep(2)  # Give backend time to start
    frontend_thread.start()
    
    print()
    print("=" * 50)
    print("  Backend: http://localhost:8000")
    print("  Frontend: http://localhost:3000")
    print("=" * 50)
    print()
    print("Press Ctrl+C to stop both servers...")
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        sys.exit(0)

if __name__ == "__main__":
    main()