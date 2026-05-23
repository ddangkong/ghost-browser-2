"""Run the existing local_worker harness, but force the browser headless.

local_worker.py hardcodes ``BrowserProfile(user_data_dir=...)`` with no
``headless``, so browser-use defaults to *headful* whenever a display exists.
On a busy desktop that cold-start exceeds browser-use's 30s BrowserStartEvent
timeout — which is exactly the "too slow / didn't finish" symptom.

This shim patches the name ``local_worker.BrowserProfile`` to inject
``headless=True`` (much faster start, no window), then delegates to the real
``local_worker.main()`` unchanged. Usage is identical:

    python gb_headless_worker.py <config.json>
"""

from __future__ import annotations

import sys
import tempfile

import os

import local_worker
from browser_use import Agent as _RealAgent
from browser_use import BrowserProfile as _RealBrowserProfile
from browser_use import ChatOllama as _RealChatOllama

from ghost_actions import build_tools


def _HeadlessProfile(*args, **kwargs):
    # Force headless (fast start, no window) and a *fresh* throwaway profile.
    # The harness's persistent ``.browser-profile`` can be left corrupt by a
    # crashed headful run, which makes CDP never come up — the exact 30s
    # "Browser did not start" hang we hit. A clean temp profile sidesteps it.
    # GB_HEADFUL=1 runs windowed (stealthier). We STILL use a fresh throwaway
    # profile by default: reusing the persistent .browser-profile across launches
    # causes a profile lock / hand-off so Chromium never opens its CDP port —
    # that, not headful itself, was the "Browser did not start" failure.
    # Set GB_PERSIST=1 to opt back into the persistent profile.
    headful = os.environ.get("GB_HEADFUL") == "1"
    kwargs.setdefault("headless", not headful)
    if os.environ.get("GB_PERSIST") != "1":
        kwargs["user_data_dir"] = tempfile.mkdtemp(prefix="gb-smoke-")
    return _RealBrowserProfile(*args, **kwargs)


def _AgentWithTools(*args, **kwargs):
    # Inject our extended tool set (adds press_and_hold) unless the caller
    # already supplied one.
    if kwargs.get("tools") is None and kwargs.get("controller") is None:
        kwargs["tools"] = build_tools()
    return _RealAgent(*args, **kwargs)


def _ChatOllamaTuned(*args, **kwargs):
    # Fix the llm_timeout failures (5/26): give each inference call a generous
    # timeout. The default is None, which on a cold/busy model could leave a
    # call hanging until an upstream abort and be recorded as a timeout.
    # Tunable via GB_LLM_TIMEOUT. (Model residency is handled separately by
    # pre-warming + the Ollama server's OLLAMA_KEEP_ALIVE.)
    kwargs.setdefault("timeout", float(os.environ.get("GB_LLM_TIMEOUT", "180")))
    return _RealChatOllama(*args, **kwargs)


local_worker.BrowserProfile = _HeadlessProfile  # type: ignore[attr-defined]
local_worker.Agent = _AgentWithTools  # type: ignore[attr-defined]
local_worker.ChatOllama = _ChatOllamaTuned  # type: ignore[attr-defined]

# In headful + persistent-profile mode, the cold Chromium start (window +
# extensions, on a busy machine) can exceed browser-use's hardcoded 30s CDP
# wait in LocalBrowserWatchdog._wait_for_cdp_url. Raise it so the stealthier
# mode can actually start. Tunable via GB_CDP_WAIT.
if os.environ.get("GB_HEADFUL") == "1":
    from browser_use.browser.watchdogs.local_browser_watchdog import LocalBrowserWatchdog as _LBW

    _orig_wait = _LBW._wait_for_cdp_url

    async def _patched_wait(port, timeout: float = float(os.environ.get("GB_CDP_WAIT", "90"))):
        return await _orig_wait(port, timeout)

    _LBW._wait_for_cdp_url = staticmethod(_patched_wait)  # type: ignore[assignment]

if __name__ == "__main__":
    raise SystemExit(local_worker.main())
