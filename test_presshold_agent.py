"""End-to-end: Gemma 4 + our press_and_hold action vs. a press-and-hold gate.

Objective check (independent of the LLM judge): after the agent runs, the local
challenge page sets document.title to 'Verified' only if the mouse button was
held with trusted CDP events for >=3s. We assert on that title.

    python test_presshold_agent.py
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import socketserver
import sys
import tempfile
import threading

from browser_use import Agent, BrowserProfile, ChatOllama

from ghost_actions import build_tools


def _serve(directory: str) -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=directory)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}", httpd


async def main() -> int:
    base, httpd = _serve("benchmark_site")
    url = f"{base}/presshold.html"
    task = (
        f"Open {url}. The page has a 'Press & Hold' button that verifies you "
        "are human. Use the press_and_hold action on that button for about 4 "
        "seconds (a normal click will NOT work — the button must be held down). "
        "Then confirm the page says you are verified."
    )

    llm = ChatOllama(model="gemma4:latest",
                     ollama_options={"temperature": 0, "num_ctx": 32768})
    profile = BrowserProfile(headless=True,
                             user_data_dir=tempfile.mkdtemp(prefix="gb-ph-"))
    agent = Agent(task=task, llm=llm, browser_profile=profile,
                  tools=build_tools(), use_vision=False, max_failures=3)
    await agent.run(max_steps=8)

    page = await agent.browser_session.must_get_current_page()
    title = await page.evaluate("() => document.title")
    used_hold = any(
        "press_and_hold" in str(a)
        for h in agent.history.history for a in (h.model_output.action if h.model_output else [])
    )
    ok = title == "Verified"
    print(f"\nRESULT: title={title!r}  press_and_hold_used={used_hold}  "
          f"=> {'PASS' if ok else 'FAIL'}")
    await agent.browser_session.kill()
    httpd.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
