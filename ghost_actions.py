"""Custom browser-use actions for Ghost Browser.

Adds the capability browser-use lacks and that caused 13 of the 26 Stealth Bench
failures: a **press-and-hold** mouse action. Many anti-bot gates ("Press & Hold
to confirm you're human", PerimeterX-style) require the *primary mouse button to
stay down at a fixed point for several seconds*. A normal click (down+up in a
few ms) never satisfies them.

We dispatch real CDP ``Input.dispatchMouseEvent`` press/release (via browser-use's
own ``Mouse`` actor, so the events are trusted, unlike JS-synthesized ones) and
hold for the requested duration with tiny human-like jitter in between.

``build_tools()`` returns a ``Tools`` instance with all the standard actions
plus ``press_and_hold``; pass it to ``Agent(tools=...)``.
"""

from __future__ import annotations

import asyncio
import random

from browser_use import Tools
from browser_use.agent.views import ActionResult
from pydantic import BaseModel, Field


class PressHoldAction(BaseModel):
    index: int = Field(description="Index of the element to press and hold.")
    seconds: float = Field(
        default=4.0,
        description="How long to hold the mouse button down, in seconds "
                    "(typical press-and-hold gates need 3-10s).",
    )


async def human_press_hold(client, session_id, cx: int, cy: int,
                           seconds: float) -> None:
    """Dispatch a trusted CDP press-and-hold at (cx, cy) for ``seconds``.

    Shared by the ``press_and_hold`` action and the automatic gate solver. We
    issue ``Input.dispatchMouseEvent`` ourselves with explicit coordinates —
    browser-use's ``Mouse.down()/up()`` hardcode (0,0) and would miss the target
    (see notes in this file's docstring). Tiny jitter during the hold keeps the
    cursor from being unnaturally frozen.
    """
    cx, cy = int(cx), int(cy)

    async def _evt(event_type: str, x: int, y: int) -> None:
        await client.send.Input.dispatchMouseEvent(
            {"type": event_type, "x": x, "y": y,
             "button": "left", "clickCount": 1},
            session_id=session_id,
        )

    hold = max(0.5, min(float(seconds), 15.0))
    await _evt("mouseMoved", cx, cy)
    await asyncio.sleep(random.uniform(0.08, 0.20))  # settle before press
    await _evt("mousePressed", cx, cy)
    elapsed = 0.0
    while elapsed < hold:
        step = min(random.uniform(0.18, 0.32), hold - elapsed)
        await asyncio.sleep(step)
        elapsed += step
        if elapsed < hold:
            await _evt("mouseMoved", cx + random.randint(-1, 1),
                       cy + random.randint(-1, 1))
    await _evt("mouseReleased", cx, cy)


def _center(node) -> tuple[int, int]:
    rect = getattr(node, "absolute_position", None)
    if rect is None:
        raise ValueError(
            f"element {getattr(node, 'element_index', '?')} has no on-screen "
            "position; scroll it into view before press-and-hold"
        )
    x = rect.x + rect.width / 2.0
    y = rect.y + rect.height / 2.0
    return int(x), int(y)


def build_tools() -> Tools:
    tools = Tools()

    @tools.action(
        "Press and hold the LEFT mouse button on an element for N seconds, then "
        "release. Use this to pass 'Press & Hold' / 'press and hold to verify "
        "you are human' anti-bot challenges that a normal click cannot solve.",
        param_model=PressHoldAction,
    )
    async def press_and_hold(params: PressHoldAction, browser_session) -> ActionResult:
        node = await browser_session.get_element_by_index(params.index)
        if node is None:
            return ActionResult(
                error=f"No element with index {params.index} to press and hold."
            )
        cx, cy = _center(node)
        page = await browser_session.must_get_current_page()
        mouse = await page.mouse
        hold = max(0.5, min(float(params.seconds), 15.0))
        await human_press_hold(mouse._client, mouse._session_id, cx, cy, hold)

        msg = f"Pressed and held element {params.index} for {hold:.1f}s at ({cx},{cy})."
        return ActionResult(extracted_content=msg, long_term_memory=msg)

    return tools
