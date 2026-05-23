"""Directly verify the press_and_hold ACTION through browser-use's CDP path.

This isolates the capability from the LLM's (flaky) tool selection: we navigate
to the local press-and-hold gate, find the button's element index from the
browser-use selector map, then invoke the registered ``press_and_hold`` action
directly via the tools registry. Success = the page sets document.title to
'Verified' (only possible with a trusted >=3s hold).

    python test_presshold_direct.py
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import socketserver
import sys
import tempfile
import threading

from browser_use import BrowserProfile, BrowserSession
from browser_use.browser.events import NavigateToUrlEvent

from ghost_actions import build_tools


def _serve(directory: str):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=directory)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}", httpd


async def main() -> int:
    base, httpd = _serve("benchmark_site")
    url = f"{base}/presshold.html"

    profile = BrowserProfile(headless=True,
                             user_data_dir=tempfile.mkdtemp(prefix="gb-phd-"))
    session = BrowserSession(browser_profile=profile)
    await session.start()
    try:
        await session.event_bus.dispatch(
            NavigateToUrlEvent(url=url)).event_result(raise_if_none=False)
        await asyncio.sleep(1.0)
        state = await session.get_browser_state_summary(include_screenshot=False)

        # find the "Press & Hold" button index in the selector map
        smap = state.dom_state.selector_map
        idx = None
        for i, node in smap.items():
            if "press" in str(node).lower() or "hold" in str(node).lower():
                idx = i
                break
        if idx is None and len(smap) == 1:
            idx = next(iter(smap))  # only one interactive element — it's the button
        if idx is None:
            print("could not find button index; selector map:", list(smap)[:10])
            return 2
        print(f"button element index = {idx}")

        tools = build_tools()
        result = await tools.registry.execute_action(
            "press_and_hold", {"index": idx, "seconds": 4.0},
            browser_session=session)
        print("action result:", getattr(result, "extracted_content", result))

        await asyncio.sleep(0.3)
        page = await session.must_get_current_page()
        title = await page.evaluate("() => document.title")
        ok = title == "Verified"
        print(f"\nRESULT: title={title!r} => {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    finally:
        await session.kill()
        httpd.shutdown()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
