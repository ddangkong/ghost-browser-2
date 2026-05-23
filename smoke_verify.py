"""Fast smoke verification for the Ghost Browser harness.

Reuses the project's real verification pipeline — ``local_worker.py`` (browser
plan → agent → guard → LLM judge ``evaluate_result``) — but runs only a handful
of simple tasks on stable public sites, headless, with a small model and a short
per-task timeout. The point is to confirm the pipeline works end-to-end and is
*fast* now, not to reproduce the full 79-task Stealth Bench.

    python smoke_verify.py --model gemma4:e2b --timeout 240

Exit code from local_worker: 0 = judge accepted (PASS), 11 = inadequate (FAIL),
anything else / timeout = ERROR.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
FINAL_START = "__BROWSER_USE_FINAL_RESULT_START__"
FINAL_END = "__BROWSER_USE_FINAL_RESULT_END__"

# Simple, verifiable tasks on stable public sites.
TASKS = [
    {"name": "example_title",
     "task": "Open https://example.com and tell me the page title."},
    {"name": "wikipedia_title",
     "task": "Open https://en.wikipedia.org/wiki/Web_browser and tell me the "
             "title of the article shown on the page."},
    {"name": "httpbin_ip",
     "task": "Open https://httpbin.org/ip and tell me the IP address shown "
             "on the page."},
]


def extract_final(stdout: str) -> str:
    if FINAL_START in stdout and FINAL_END in stdout:
        return stdout.split(FINAL_START, 1)[1].split(FINAL_END, 1)[0].strip()
    return ""


def run_one(task: dict, *, model: str, timeout: int) -> dict:
    cfg = {
        "task": task["task"], "model": model, "temperature": 0,
        "num_ctx": 32768, "max_steps": 6, "max_attempts": 1,
        "strategy": "auto", "use_vision": False,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(cfg, f)
        cfg_path = f.name

    env_worker = HERE / "gb_headless_worker.py"
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(env_worker), cfg_path],
            cwd=str(HERE), capture_output=True, text=True, timeout=timeout,
            env={**_env()},
        )
        dur = time.time() - t0
        code = proc.returncode
        final = extract_final(proc.stdout)
        status = {0: "PASS", 11: "FAIL"}.get(code, f"ERR({code})")
    except subprocess.TimeoutExpired:
        dur = time.time() - t0
        status, final = "TIMEOUT", ""
    return {"name": task["name"], "status": status,
            "duration_sec": round(dur, 1), "final": final[:200]}


def _env() -> dict:
    import os
    e = dict(os.environ)
    e.setdefault("ANONYMIZED_TELEMETRY", "false")
    e.setdefault("BROWSER_USE_TELEMETRY", "false")
    return e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:latest")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    print(f"Ghost Browser smoke verify — model={args.model}, "
          f"timeout={args.timeout}s, headless\n")
    results, t0 = [], time.time()
    for task in TASKS:
        print(f"  running {task['name']} …", flush=True)
        r = run_one(task, model=args.model, timeout=args.timeout)
        results.append(r)
        print(f"    {r['status']:8} {r['duration_sec']:>6.1f}s  "
              f"{r['final'][:80]!r}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    total_time = time.time() - t0
    summary = {
        "model": args.model, "tasks": len(results), "passed": passed,
        "accuracy": round(passed / len(results), 3) if results else 0.0,
        "wall_time_sec": round(total_time, 1), "results": results,
    }
    out = HERE / "smoke_results.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"\n  PASSED {passed}/{len(results)}  "
          f"({summary['accuracy']:.0%})  in {total_time:.0f}s")
    print(f"  wrote {out.name}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
