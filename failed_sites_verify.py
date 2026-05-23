"""Re-run the SITES that failed in Stealth Bench V1 — best-effort reconstruction.

IMPORTANT: the original benchmark only stored task_id + score + failure_reason,
not the original task instructions. The instructions below are *reconstructed*
plausible navigation goals for each failed site, grouped by the original failure
category, so we can observe how the (now headless, fresh-profile) harness behaves
on them today. This is diagnostic, not an apples-to-apples bench rerun.

    python failed_sites_verify.py --model gemma4:latest --timeout 220
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from smoke_verify import run_one  # reuse the headless harness runner

HERE = Path(__file__).parent

# (name, category, reconstructed task)
FAILED = [
    ("reddit_top", "llm_timeout",
     "Open https://www.reddit.com/r/popular/ and tell me the title of the "
     "first post you can see."),
    ("x_home", "llm_timeout",
     "Open https://x.com and tell me what the page shows (headline, login "
     "prompt, or main content)."),
    ("walmart_search", "press_hold",
     "Open https://www.walmart.com and search for 'AirPods', then tell me the "
     "price of the first result."),
    ("fiverr_categories", "press_hold",
     "Open https://www.fiverr.com and tell me one category of services listed "
     "on the homepage."),
    ("homedepot_home", "cloudflare_access_denied",
     "Open https://www.homedepot.com and tell me the main heading or any "
     "product category shown."),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:latest")
    ap.add_argument("--timeout", type=int, default=220)
    ap.add_argument("--headful", action="store_true",
                    help="run headful + persistent profile (stealthier, slower)")
    args = ap.parse_args()

    if args.headful:
        # Stealthier mode: keep the window + persistent profile, and allow a
        # long cold-start (real Chromium + extensions can exceed the 30s default).
        os.environ["GB_HEADFUL"] = "1"
        os.environ.setdefault("TIMEOUT_BrowserLaunchEvent", "180")
        os.environ.setdefault("TIMEOUT_BrowserStartEvent", "180")

    mode = "headful" if args.headful else "headless"
    print(f"Failed-site re-run — model={args.model}, timeout={args.timeout}s, "
          f"{mode} (reconstructed tasks)\n")
    results, t0 = [], time.time()
    for name, category, task in FAILED:
        print(f"  running {name} [{category}] …", flush=True)
        r = run_one({"name": name, "task": task},
                    model=args.model, timeout=args.timeout)
        r["category"] = category
        results.append(r)
        print(f"    {r['status']:8} {r['duration_sec']:>6.1f}s  "
              f"{r['final'][:80]!r}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    summary = {
        "model": args.model, "note": "reconstructed tasks, diagnostic only",
        "tasks": len(results), "passed": passed,
        "wall_time_sec": round(time.time() - t0, 1), "results": results,
    }
    summary["mode"] = mode
    out_name = ("failed_sites_results_headful.json" if args.headful
                else "failed_sites_results.json")
    (HERE / out_name).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  PASSED {passed}/{len(results)}  in {summary['wall_time_sec']:.0f}s")
    print(f"  wrote {out_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
