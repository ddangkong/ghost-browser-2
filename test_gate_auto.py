"""Verify the automatic press-and-hold gate solver — no LLM instruction.

Navigate to the local gate, run the detector + human hold, assert the page
flips to 'Verified'. This proves the harness can clear a press-and-hold gate on
its own, independent of whether the model picks the right tool.

    python test_gate_auto.py
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

from gate_solver import detect_press_hold, solve_press_hold


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
                             user_data_dir=tempfile.mkdtemp(prefix="gb-ga-"))
    session = BrowserSession(browser_profile=profile)
    await session.start()
    try:
        await session.event_bus.dispatch(
            NavigateToUrlEvent(url=url)).event_result(raise_if_none=False)
        await asyncio.sleep(1.0)

        page = await session.must_get_current_page()
        detected = await detect_press_hold(page)
        print(f"detected gate: {detected}")
        acted = await solve_press_hold(session, seconds=4.0)
        print(f"solved control text: {acted!r}")

        await asyncio.sleep(0.3)
        title = await page.evaluate("() => document.title")
        ok = detected is not None and title == "Verified"
        print(f"\nRESULT: title={title!r} => {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    finally:
        await session.kill()
        httpd.shutdown()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
