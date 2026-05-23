"""Automatic press-and-hold gate solver (guard-layer extension).

Small local Gemma models reliably *recognize* a press-and-hold gate but don't
reliably *select* the press_and_hold action — they keep retrying click. Rather
than depend on the model's tool choice, this detects a press-and-hold control on
the current page and solves it deterministically with a human-like trusted hold.

It fits the project's existing philosophy (guard layer + auto-recovery): the
harness handles the interaction the agent can't express. Detection is
language-aware (English + Korean) and matches the visible control text.
"""

from __future__ import annotations

from ghost_actions import human_press_hold

# Returns the first visible press-and-hold control's center coordinates + text.
_DETECT_JS = r"""
() => {
  const re = /(press\s*&?\s*(and\s*)?hold)|(hold\b.*(verify|human|confirm|continue|to))|(tap\s*(and\s*)?hold)|(꾹\s*누르)|(누르고\s*(있|계|유지))|(길게\s*누르)/i;
  const nodes = Array.from(document.querySelectorAll(
    'button,a,div,span,[role=button],input[type=button],input[type=submit]'));
  for (const el of nodes) {
    const t = (el.innerText || el.value || el.textContent || '').trim();
    if (!t || t.length > 80) continue;
    if (!re.test(t)) continue;
    const b = el.getBoundingClientRect();
    if (b.width > 0 && b.height > 0 &&
        getComputedStyle(el).visibility !== 'hidden') {
      return {found: true, text: t.slice(0, 60),
              cx: Math.round(b.x + b.width / 2),
              cy: Math.round(b.y + b.height / 2)};
    }
  }
  return {found: false};
}
"""


async def detect_press_hold(page) -> dict | None:
    """Return {text, cx, cy} for a press-and-hold control, or None."""
    import json
    raw = await page.evaluate(_DETECT_JS)
    data = raw if isinstance(raw, dict) else json.loads(raw)
    return data if data.get("found") else None


async def solve_press_hold(session, *, seconds: float = 4.0) -> str | None:
    """If the current page shows a press-and-hold gate, hold it like a human.

    Returns the control text it acted on, or None if no gate was found.
    """
    page = await session.must_get_current_page()
    ctrl = await detect_press_hold(page)
    if not ctrl:
        return None
    mouse = await page.mouse
    await human_press_hold(mouse._client, mouse._session_id,
                           ctrl["cx"], ctrl["cy"], seconds)
    return ctrl["text"]
