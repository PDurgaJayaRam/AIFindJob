"""Server entry point - forces ProactorEventLoop for Playwright on Windows.

Uvicorn's default asyncio setup forces SelectorEventLoop on Windows when
reload=True, which breaks Playwright's subprocess creation. We monkey-patch
uvicorn's loop setup to use ProactorEventLoop instead.
"""
import sys
import asyncio

# MUST be set before uvicorn imports anything
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Monkey-patch uvicorn's loop factory to ALWAYS use ProactorEventLoop on Windows.
    # Uvicorn returns SelectorEventLoop when use_subprocess=True, but SelectorEventLoop
    # cannot create subprocesses on Windows — breaking Playwright/CloakBrowser.
    try:
        import uvicorn.loops.asyncio as _loop_mod
        def _always_proactor(use_subprocess: bool = False):
            return asyncio.ProactorEventLoop
        _loop_mod.asyncio_loop_factory = _always_proactor
    except Exception:
        pass

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
