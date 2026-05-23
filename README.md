# Ghost Browser 2

> **Free, local browser-automation agent powered by Codex (ChatGPT OAuth) + a custom interaction layer.**
> Scores **82.5% on Stealth Bench V1 (66/80)** — outperforms the commercial #1 (`browser-use-cloud`, 73.8%) by **+8.7 pp** and the v1 Ghost Browser (Gemma 27B, 67.1%) by **+15.4 pp**.

> Research / benchmarking tool. Results are environment-dependent and not a guarantee of bypassing any specific protection.

---

## Stealth Bench V1 — Results

| Rank | Agent | Tasks | Passed | Accuracy | Type |
|------|-------|------:|-------:|--------:|------|
| **1 ⭐** | **Ghost Browser 2 (Codex + `press_and_hold`)** | **80** | **66** | **82.5%** | **💻 Local / OAuth** |
| 2 | browser-use-cloud | 80 | 59 | 73.8% | ☁️ Paid cloud |
| 3 | anchor | 79 | 55 | 69.6% | ☁️ Paid cloud |
| 4 | Ghost Browser v1 (Gemma 27B) | 79 | 53 | 67.1% | 💻 Local |
| 5 | onkernel | 80 | 53 | 66.2% | ☁️ Paid cloud |
| 6 | browserless | 80 | 42 | 52.5% | ☁️ Paid cloud |
| 7 | local_headful (bu-2-0) | 80 | 40 | 50.0% | 💻 Local |

Full per-task data in [`bench_v2_results.json`](bench_v2_results.json).

### Category breakdown (this run)

| Category | Pass | Rate |
|----------|------|-----:|
| reCaptcha                       | 6/6   | **100%** |
| hCaptcha                        | 3/3   | **100%** |
| Shape                           | 1/1   | 100%  |
| Temu Slider                     | 1/1   | 100%  |
| Cloudflare                      | 20/22 | 90.9% |
| Datadome                        | 11/13 | 84.6% |
| Akamai                          | 5/6   | 83.3% |
| Custom Antibot                  | 4/5   | 80.0% |
| GeeTest                         | 3/4   | 75.0% |
| **PerimeterX (press & hold)**   | **12/18** | **66.7%** |
| Kasada                          | 0/1   | 0%    |

### Reproducibility

| Field | Value |
|-------|-------|
| Date              | 2026-05-23 |
| Model             | `gpt-5.5` via Codex CLI (ChatGPT OAuth — no API key) |
| Backend           | `codex-oai-proxy` (port 8787, OpenAI-compatible) |
| Browser           | `local_headful` (Chromium + per-task fresh profile) |
| Harness           | `browser-use 0.12.6` + `GB_TOOLS=1` injection |
| Parallel          | 3 |
| Per-task timeout  | 1800 s |
| Wall time         | ~3.6 h |
| OS                | Windows 11 |

---

## What Ghost Browser 2 adds over v1

| | v1 (Ghost Browser by Gemma) | **v2 (this repo)** |
|---|---|---|
| Model | Gemma 4 27B local (Ollama) | **`gpt-5.5` via Codex CLI OAuth** (no API key) |
| Press-and-hold action | ❌ Missing (13/26 v1 failures were PerimeterX) | ✅ [`ghost_actions.py`](ghost_actions.py) — trusted CDP press/hold with human jitter |
| Auto gate solver | ❌ | ✅ [`gate_solver.py`](gate_solver.py) — detect-and-hold without model instruction |
| Headful startup | Could hang on persistent profile | ✅ Fresh per-task profile; root cause documented |
| Window cleanup | Leaked on success path | ✅ `browser.stop()` on every path |
| LLM call timeout | Default `None`, occasional hangs | ✅ Tunable, defaults 180–300 s |
| Stealth Bench V1 | 67.1% | **82.5%** |

---

## Architecture

```
Task
 ↓
run_eval.py (browser-use Agent loop)
 ├─ create_llm    → ChatOpenAI(base_url=http://127.0.0.1:8787/v1, model="gpt-5.5")
 │                          │
 │                          ▼
 │                   codex-oai-proxy ──► codex CLI ──► OpenAI (ChatGPT OAuth)
 │
 ├─ create_browser → Browser(headless=False, user_data_dir=tempfile)  (fresh per task)
 │
 └─ Agent(tools=ghost_actions.build_tools(),
          register_new_step_callback=gate_solver.solve_press_hold)
              │
              ▼
       press_and_hold  +  auto press-and-hold gate detector
```

---

## What Ghost Browser 2 still does NOT solve

The 14 remaining failures are all environment-bound:

| Reason | Count | Examples |
|---|---:|---|
| Korean ISP geo-blocked by US sites | 5 | gamestop, bloomberg, homedepot, crocs, douyin |
| Site temporarily down | 1 | belk |
| Slider / image CAPTCHA (not press-hold) | 8 | zoro, zillow, ralphlauren, seatgeek, idealista, tripadvisor, lianjia, bathandbodyworks |

A US residential proxy would likely recover the first 5 (pushing the score to ~89%). Slider/image CAPTCHA needs a different capability than what ships here.

---

## Setup

```powershell
# 1. OpenAI Codex CLI + ChatGPT Plus/Pro/Enterprise login
npm install -g @openai/codex
codex login

# 2. codex-oai-proxy — exposes Codex CLI as an OpenAI-compatible HTTP endpoint
git clone https://github.com/ddangkong/codex-oai-proxy
cd codex-oai-proxy
.\start.ps1 -Port 8787 -Model gpt-5.5

# 3. browser-use Stealth Benchmark (upstream)
git clone https://github.com/browser-use/browser-use-benchmarks stealth-benchmark
cd stealth-benchmark
uv sync
git apply ../ghost-browser-2/stealth_bench_patch/run_eval.patch

# 4. Run
$env:GB_TOOLS         = "1"
$env:OPENAI_BASE_URL  = "http://127.0.0.1:8787/v1"
$env:OPENAI_API_KEY   = "sk-no-key-needed"
uv run python run_eval.py --suite stealth --browser local_headful `
   --model openai:gpt-5.5 --parallel 3 --task-timeout 1800
```

---

## Verifying the press-and-hold capability in isolation (fast, no LLM needed)

```powershell
python -m http.server --directory benchmark_site 8000   # serves the local gate

# In another shell:
python test_presshold_direct.py   # uses press_and_hold action via CDP
python test_gate_auto.py          # uses gate_solver detect+hold (no LLM)
```

Both should print `RESULT: title='Verified' => PASS`.

---

## Files

| File | Purpose |
|---|---|
| `ghost_actions.py` | Registers the `press_and_hold` action for browser-use's tool registry |
| `gate_solver.py` | Detects and auto-solves press-and-hold gates without LLM instruction |
| `gb_headless_worker.py` | Profile / headful / tool injection wrapper for v1's `local_worker.py` |
| `codex_client.py` | Standalone subprocess wrapper for `codex exec` (alternative to the proxy) |
| `stealth_bench_patch/run_eval.patch` | Diff against browser-use's `run_eval.py` adding OpenAI backend, tool injection, gate-solver hook, per-task profile, success-path `browser.stop()` |
| `benchmark_site/presshold.html` | Local press-and-hold gate (rejects synthetic events) |
| `test_presshold_*.py`, `test_gate_auto.py` | Objective in-isolation verification of the capability |
| `bench_v2_results.json` | This repo's run on Stealth Bench V1 (66/80) |
| `benchmark_results.json` | v1's original run (53/79) for comparison |

---

## Built on / borrowed from

This release stands on a handful of open-source pieces. Below is what was
actually pulled in and how — credit and licenses included.

### Directly merged / vendored into this repo

| Source | Role here | License |
|---|---|---|
| **[`ddangkong/ghost-browser` (v1)](https://github.com/ddangkong/ghost-browser)** | The v1 harness — `local_worker.py`'s reflexion-retry loop, guard layer, auto-recovery, partial-result saving. v2 keeps the spirit and adds the missing capability (`press_and_hold`) plus the OpenAI/Codex backend. `benchmark_results.json` is carried over for direct v1↔v2 comparison. | MIT |
| **[`browser-use/browser-use` v0.12.6](https://github.com/browser-use/browser-use)** | The underlying agent framework. v2 keeps it vendored exactly as v1 did, and extends it via the `Tools` registry (`ghost_actions.py`) and `register_new_step_callback` hook (`gate_solver.py`) — no fork, no patch. Also exposed a **mouse-coordinate bug in `browser_use/actor/mouse.py`** (`Mouse.down()/up()` hardcode `x=0,y=0`) that v2 routes around by dispatching CDP `Input.dispatchMouseEvent` ourselves. | Apache 2.0 |

### External tools v2 plugs into (used but not vendored)

| Source | How v2 uses it |
|---|---|
| **[`browser-use/browser-use-benchmarks`](https://github.com/browser-use/browser-use-benchmarks)** (the Stealth Bench V1 harness) | The official test suite. v2 ships a small patch — [`stealth_bench_patch/run_eval.patch`](stealth_bench_patch/run_eval.patch) — that adds the OpenAI-compatible backend, the `GB_TOOLS` injection point, the gate-solver step hook, a per-task fresh profile, and `browser.stop()` on the success path. Apply on top of the upstream repo. |
| **[`openai/codex`](https://github.com/openai/codex)** (Codex CLI) | The agent's brain. v2 calls `codex exec` either through `codex-oai-proxy` (default, OpenAI-compatible) or directly via [`codex_client.py`](codex_client.py)'s subprocess wrapper. Uses your ChatGPT Plus/Pro OAuth login — no API key. |
| **[`codex-oai-proxy`](https://github.com/ddangkong/codex-oai-proxy)** | Exposes Codex CLI as an OpenAI-compatible HTTP endpoint. v2's `run_eval.py` patch points `ChatOpenAI(base_url=…)` at it. Without the proxy, fall back to `codex_client.py`. |

### Considered but NOT merged

| Source | Why it's listed | Status |
|---|---|---|
| **[`CloakHQ/CloakBrowser`](https://github.com/CloakHQ/CloakBrowser)** | We benchmarked v2 against it and reviewed the architecture. CloakBrowser operates at a **lower layer** (58 C++ source-level patches to the Chromium binary covering canvas/WebGL/audio/fonts/WebRTC/automation signals); v2 operates at the **action/agent layer above the browser**. They're complementary, not competing — pointing browser-use's `executable_path` at the CloakBrowser binary would stack the two cleanly. Not done in this release; documented as a future integration path. | Future |

## License

MIT for this repo. See the table above for the upstream licenses of each
component v2 builds on.

---

## Honest caveats

- The 82.5% was produced from a **Korean ISP** egress IP. Sites that geo-block KR (~5 of the failures) would likely pass from a US residential proxy.
- The Codex backend goes through a ChatGPT Plus/Pro OAuth session via `codex-oai-proxy`. This consumes your ChatGPT quota (about ~12 M tokens for a full Stealth Bench V1 run).
- The auto gate solver's regex is permissive and can false-positive on UI text containing the words "press" / "hold". Tune `_DETECT_JS` if needed.
- Slider / image / drag CAPTCHAs are out of scope here.
