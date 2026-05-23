"""Codex CLI backend — drive the browser with OpenAI's Codex via your ChatGPT login.

Subprocess-calls ``codex exec --skip-git-repo-check -`` with the same prompt
shape we send to Ollama, captures stdout, and extracts the assistant's
``{...}`` JSON action. No API key needed — Codex CLI uses your existing OAuth
login (``codex login``).

Caveats:
- Each call spins up the CLI (~5-15s) and sends Codex's full system prompt,
  so each step is ~20k tokens of overhead. Quota-sensitive.
- Codex is an *agentic* CLI; we keep it on rails by demanding JSON-only output
  in the system message. Trailing CLI chatter ("tokens used" etc.) is stripped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field


def _default_binary() -> str:
    # On Windows the codex shim is ``codex.cmd``; Python's subprocess won't find
    # the bare ``codex`` name without ``shell=True``. Resolve a usable path now.
    for candidate in ("codex.cmd", "codex.exe", "codex"):
        path = shutil.which(candidate)
        if path:
            return path
    return "codex"

__all__ = ["CodexClient", "CodexError"]


class CodexError(RuntimeError):
    pass


@dataclass
class CodexClient:
    """Same surface as :class:`OllamaClient`: ``available()`` and ``chat(...)``."""

    binary: str = field(default_factory=_default_binary)
    timeout: float = 90.0
    # Vision is not exposed by ``codex exec`` in a portable way; we ignore the
    # ``images`` kwarg so callers can swap clients without changing call sites.

    def chat(self, messages: list[dict], *, images: list[str] | None = None,
             json_mode: bool = True) -> str:
        # Flatten the chat into a single prompt: Codex CLI's stdin is a free-form
        # instruction, not a structured message list.
        system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        rest = "\n\n".join(
            f"{m.get('role','user').upper()}: {m['content']}"
            for m in messages if m.get("role") != "system"
        )
        prompt = (
            (system + "\n\n" if system else "")
            + rest
            + "\n\nRespond with EXACTLY one JSON object as your action — no prose, "
              "no code fences, no shell commands. Do not call any tools."
        )

        try:
            proc = subprocess.run(
                [self.binary, "exec", "--skip-git-repo-check", "-"],
                input=prompt, capture_output=True, text=True,
                timeout=self.timeout, encoding="utf-8", errors="replace",
            )
        except FileNotFoundError as e:
            raise CodexError(
                f"codex CLI not found on PATH (`{self.binary}`). "
                "Install it and run `codex login`."
            ) from e
        except subprocess.TimeoutExpired as e:
            raise CodexError(f"codex exec timed out after {self.timeout}s") from e
        if proc.returncode != 0:
            raise CodexError(
                f"codex exec failed (exit {proc.returncode}): "
                f"{(proc.stderr or '').strip()[:300]}"
            )
        return _extract_action(proc.stdout)

    def available(self) -> bool:
        try:
            r = subprocess.run([self.binary, "--version"], capture_output=True,
                               text=True, timeout=5)
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False


# Codex CLI stdout looks like:
#     user
#     <our prompt>
#
#     codex
#     {"action":"done","answer":"..."}
#     tokens used
#     22049
# We want the assistant's JSON action — the last balanced {...} in the stream
# that actually parses as JSON. Python's ``re`` has no recursive groups so we
# scan brace pairs by hand.


def _extract_action(stdout: str) -> str:
    text = stdout.strip()
    # Cheap balanced-braces scan from the end backward.
    best = ""
    depth = 0
    end = -1
    for i in range(len(text) - 1, -1, -1):
        c = text[i]
        if c == "}":
            if depth == 0:
                end = i
            depth += 1
        elif c == "{":
            depth -= 1
            if depth == 0 and end > i:
                candidate = text[i:end + 1]
                # Prefer the latest object that actually parses as JSON.
                try:
                    json.loads(candidate)
                    best = candidate
                    break
                except json.JSONDecodeError:
                    end = -1  # keep scanning further left
    return best or text
