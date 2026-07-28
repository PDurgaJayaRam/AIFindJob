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
import socket
import os
from pathlib import Path


def kill_port(port=8000):
    """Kill any process holding the given port (Windows) and wait until port is free."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, timeout=5)
    except Exception:
        pass
    # Wait until port is actually free
    for _ in range(10):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                time.sleep(0.5)
        except OSError:
            return True
    return False


def wait_for_backend(port=8000, timeout=30):
    """Wait for port to become free, then wait for it to be taken by the new backend."""
    # First: ensure port is free (kill succeeded)
    for _ in range(20):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                time.sleep(0.5)
        except OSError:
            break

    # Now wait for new backend to bind the port
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False

def run_backend():
    """Run FastAPI backend."""
    print("[BACKEND] Starting FastAPI on port 8000...")
    import os
    env = os.environ.copy()
    # Ensure PYTHONPATH includes project root
    project_root = Path(__file__).parent
    env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get("PYTHONPATH", "")
    
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
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
    
    # Kill any stale process on port 8000
    kill_port(8000)
    
    # Start both processes in threads
    backend_thread = threading.Thread(target=run_backend, daemon=True)
    frontend_thread = threading.Thread(target=run_frontend, daemon=True)
    
    backend_thread.start()

    print("[BACKEND] Waiting for backend to be ready...")
    if wait_for_backend():
        print("[BACKEND] Backend is ready!")
    else:
        print("[BACKEND] WARNING: Backend did not become ready in time, starting frontend anyway")

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