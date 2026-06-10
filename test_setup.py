"""Quick test script to verify JOBFinder setup."""
import os
import sys
from pathlib import Path

# Load .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

print("=" * 60)
print("  JOBFinder Setup Verification")
print("=" * 60)

# Check API keys
nvidia_key = os.getenv("NVIDIA_API_KEY", "")
primary = os.getenv("PRIMARY_AI_PROVIDER", "nvidia")
print(f"\n[OK] NVIDIA API Key: {'Set' if nvidia_key else 'Missing!'}")
print(f"[OK] Primary Provider: {primary}")

# Test imports
try:
    from database.engine import init_db, async_session
    print("[OK] Database engine imports OK")
except Exception as e:
    print(f"[FAIL] Database import error: {e}")

try:
    from ingestion.engine import run_all_sources, default_sources
    print(f"[OK] Ingestion engine imports OK ({len(default_sources())} sources available)")
except Exception as e:
    print(f"[FAIL] Ingestion import error: {e}")

try:
    from ai.ai_client import get_ai_client
    client = get_ai_client()
    print(f"[OK] AI client initialized (provider: {client.provider})")
except Exception as e:
    print(f"[FAIL] AI client error: {e}")

try:
    from matching.scorer import score_job
    test_result = score_job(
        job_text="Java developer with Spring Boot experience",
        job_skills=["java", "spring boot", "mysql"],
        user_skills=["java", "python", "sql"],
        target_roles=["developer"],
        is_fresher=True
    )
    print(f"[OK] Matching scorer works (test score: {test_result['score']})")
except Exception as e:
    print(f"[FAIL] Matching scorer error: {e}")

print("\n" + "=" * 60)
print("  Ready to run: python run_dev.py")
print("  Frontend: http://localhost:3000")
print("  Backend:  http://localhost:8000")
print("=" * 60)