# How to use the golden set to improve parse accuracy

**Goal:** Increase the share of meals that parse “correctly” (match your golden set and pass checks) toward 80%, by changing one thing at a time and measuring every time.

This doc tells you exactly what to do, what to press, and how to know it’s working. No shortcuts.

---

## What you need before you start

1. **A frozen golden set**  
   The golden set lives in **PocketBase** (collection `golden_entries`). You can build it in the dashboard (**Regression** → **Golden set builder**: load recent meals, edit ingredients, add selected, or add single meals from a day with “Add to golden set”). You can clear it via **Clear golden set** in the builder or via `POST /regression/golden-clear`. For a one-time import from the old file, use `POST /regression/golden-import` with a body like `{ "entries": [ { "input": { "text": "..." }, "expected": { "ingredients": [...] }, "category": "normal" }, ... ] }` (same shape as `golden_set.json`).  
   Once you start measuring accuracy, **stop editing or adding entries** for a while. You’re trying to improve the *same* test set.

2. **API keys**  
   In `ml-pipeline/nutrition-pipeline/.env` you need:
   - `OPENAI_API_KEY`
   - `USDA_KEY`  
   If either is missing, runs will fail or return empty.

3. **Terminal**  
   You’ll run commands from the repo. All commands below assume you’re in:
   ```text
   ml-pipeline/nutrition-pipeline
   ```

---

## The one number that matters (for “is it working?”)

**Pass rate on the golden set**

- You run the golden set → the script (or API) tells you: **X passed, Y failed, Z total** and **pass rate = X/Z (e.g. 65%)**.
- **“It’s working”** = that pass rate goes **up** (or at least doesn’t go **down**) when you add a change.
- **“It’s not working”** = pass rate goes down or stays flat after a change. Then you revert or try a different change.

You’ll also use:
- **Which specific entries failed** (so you can see if you fixed one thing but broke another).
- **The log file** `regression/golden_results.jsonl` to compare “before” vs “after” numbers over time.

---

## Part A: Run the golden set (the main accuracy check)

### Option 1: Terminal (recommended so you always use the same env)

1. Open a terminal.
2. Go to the nutrition pipeline folder:
   ```bash
   cd ml-pipeline/nutrition-pipeline
   ```
   (If you’re already in the repo root, use the full path or `cd ml-pipeline/nutrition-pipeline` from there.)

3. Run the golden set (full pipeline: parser + rules + common_sense):
   ```bash
   USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py
   ```
   The script loads the golden set from the **Parse API** if `PARSE_API_URL` (or `PARSE_API_BASE`) is set; otherwise it falls back to `regression/golden_set.json` if that file exists. Set `PARSE_API_URL` to your running parse API base URL (e.g. `http://localhost:5001`) when the golden set is in PocketBase.

4. **What you’ll see:**
   - A line like: `Running golden set: N entries (tier=full, version=unknown)`
   - For each **failing** entry: `FAIL <id> (easy|normal|evil): <first 60 chars of text>...` and a few failure reasons.
   - At the end:
     - `Summary: X passed, Y failed, Z total (pass_rate%)`
     - `By category: {...}` (pass/fail per easy/normal/evil if you use categories)
     - `Logged to .../regression/golden_results.jsonl`

5. **What “working” looks like here:**  
   The script finishes without crashing. You get a clear **pass count** and **pass rate**. That’s your current accuracy number. Write it down or remember it (e.g. “baseline: 12/20 = 60%”).

### Option 2: Dashboard

1. Open the app and go to the **Regression** / **Regression Suite** view (where you run regression).
2. Find the **“Run golden set”** button (or section that runs the golden set).
3. Click **“Run golden set”**.
4. **What you’ll see:**  
   A list of results: each entry is pass or fail, often with expandable failure messages and actual ingredients.
5. **What “working” looks like:**  
   You get a list of pass/fail and can count: **X passed out of Z total** → pass rate = X/Z. That’s your accuracy.  
   Note: the dashboard may not append to `golden_results.jsonl` unless the API is called with `?log=1` or the right header. For a strict “before/after” log, use the terminal and `run_golden.py`.

---

## Part B: Establish a baseline (do this once)

Before you change any code or prompts:

1. **Run the golden set once** (Part A, Option 1):
   ```bash
   cd ml-pipeline/nutrition-pipeline
   USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py
   ```
2. **Write down:**
   - Pass rate: _____ %
   - Pass count / total: _____ / _____
   (Optional: note how many failed in easy vs normal vs evil if you use categories.)

3. **Optional but useful:** Tag this run in the log so you can find it later:
   ```bash
   PARSE_PROMPT_VERSION=baseline USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py
   ```
   That appends a line to `regression/golden_results.jsonl` with `"version": "baseline"`. Now you have a “before” snapshot.

You’ll compare every future run to this baseline (or to the previous run).

---

## Part C: The “one change at a time” loop

This is the core workflow. Do it every time you want to improve accuracy.

### Step 1: Decide the one thing you’re changing

Examples:
- A single prompt tweak in `parser_gpt.py`
- One new rule in `common_sense_rules.yaml`
- One fix in `lookup_usda.py` (e.g. tea matching)

**Do not** change two or three things in one go. You won’t know which change helped or hurt.

### Step 2: Make that one change in the code

Edit the file(s), save.

### Step 3: Run the golden set again

Same command as in Part A (Option 1):

```bash
cd ml-pipeline/nutrition-pipeline
USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py
```

If you want this run labeled in the log (e.g. “after tea fix”):

```bash
PARSE_PROMPT_VERSION=after-tea-fix USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py
```

### Step 4: Compare to before

- **New pass rate** = (passed / total) from the summary line.
- Compare to your baseline (or last run):
  - **Pass rate went up** → the change helped. Keep it. You can commit and then do another “one change” cycle.
  - **Pass rate went down** → the change hurt. Revert the code, run again to confirm you’re back to the previous pass rate, then try a different change.
  - **Pass rate unchanged** → the change didn’t move the needle. You can keep it if it doesn’t hurt, or revert and try something else.

### Step 5: Look at *which* entries failed (optional but useful)

- In the terminal output, failures are listed with `FAIL <id> ...` and short reasons.
- If you fixed one meal but another started failing, that’s a regression. Either refine the change so that meal doesn’t regress, or revert.

Then repeat: next “one change” → run golden set → compare → keep or revert.

---

## Part D: Using the log file (golden_results.jsonl)

Every time you run `run_golden.py`, it **appends one line** to:

```text
ml-pipeline/nutrition-pipeline/regression/golden_results.jsonl
```

Each line is JSON. Example:

```json
{"timestamp": "2026-02-14T...", "version": "baseline", "tier": "full", "pass_count": 12, "fail_count": 8, "total": 20, "pass_rate": 60.0, "by_category": {"easy": {"pass": 5, "fail": 0}, "normal": {"pass": 4, "fail": 3}, "evil": {"pass": 3, "fail": 5}}}
```

- **What to compare:**  
  `pass_rate` and `pass_count`/`total` between two lines (e.g. version=baseline vs version=after-tea-fix).
- **How to know it’s working:**  
  Later lines have **higher** `pass_rate` (or at least not lower) than earlier ones for the same tier.

You can open `golden_results.jsonl` in an editor and search for your `PARSE_PROMPT_VERSION` values to compare.

---

## Part E: MVP vs full pipeline (when to use which)

- **Full (default):**  
  Parser + USDA/GPT + deterministic rules + common_sense. This is what production uses. Use this for almost all of your “did my change help?” runs.

- **MVP:**  
  Parser + USDA/GPT only (no rules, no common_sense). Use this only when you explicitly want to measure “raw” parsing without any fixes.

To run with MVP:

```bash
PARSE_FLOW_TIER=mvp USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py
```

Compare MVP pass rate to full pass rate to see how much the rules + common_sense step help.

---

## Part F: Stability check (optional – “is the prompt ambiguous?”)

Sometimes pass rate is low not because the logic is wrong but because the model gives different answers on different runs (even at temp=0). You can check that with the stability script:

```bash
cd ml-pipeline/nutrition-pipeline
USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_stability.py
```

- It runs each golden meal **several times** and checks if the outputs are the same.
- **What you’ll see:**  
  “Exact-structure match rate”, “Mean field stability”, and which entries had variance.
- **How to use it:**  
  If stability is low (e.g. same meal parses differently run to run), tighten the prompt or schema first; then use the golden set again to measure accuracy.

---

## Quick reference: commands you’ll use most

| What you want to do | Command (from `ml-pipeline/nutrition-pipeline`) |
|---------------------|--------------------------------------------------|
| Run golden set (accuracy check) | `USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py` |
| Run golden set and tag version for log | `PARSE_PROMPT_VERSION=my-tag USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py` |
| Run golden set with MVP only | `PARSE_FLOW_TIER=mvp USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py` |
| Run stability check | `USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_stability.py` |
| Run regression meals (declarative suite) | `USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_regression.py` |

---

## How to know it’s working (summary)

1. **Script runs:** You get a summary line with pass count and pass rate. No crash, no “module not found” or missing key errors.
2. **You have a baseline:** You wrote down (or logged) the pass rate before changes.
3. **You compare after each change:** New pass rate &gt;= previous → change is good or neutral. New pass rate &lt; previous → revert or adjust.
4. **Log file grows:** Each `run_golden.py` run adds one line to `golden_results.jsonl` so you can see history and compare versions.

If you follow this loop (one change → run golden set → compare → keep or revert), you’re using the tool correctly to increase accuracy.
