import sys
import asyncio
import os
from pathlib import Path

# Set working directory and path
os.chdir(r"C:\Harshith Games\project dj\AIFindJob")
sys.path.insert(0, r"C:\Harshith Games\project dj\AIFindJob")

# Windows fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Now import
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import uvicorn
uvicorn.run("api.main:app", host="127.0.0.1", port=8000)