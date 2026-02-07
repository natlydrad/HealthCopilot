#!/usr/bin/env python3
"""
Learn common-sense rules from user corrections. Fetches recent corrections,
sends to GPT to propose rule updates, and merges into common_sense_rules.yaml.
No manual editing needed - GPT notices patterns and updates the rules.

Usage:
  python learn_rules_from_corrections.py              # Update rules from last 7 days
  python learn_rules_from_corrections.py --dry-run    # Preview without writing
  python learn_rules_from_corrections.py --since-days 14

Run weekly (cron) or after a batch of corrections. Restart parse API after update.
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

import yaml
import requests
from openai import OpenAI

RULES_PATH = Path(__file__).parent / "common_sense_rules.yaml"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PB_URL = os.getenv("PB_URL") or "http://127.0.0.1:8090"

# Import after load_dotenv
def _get_token():
    from pb_client import get_token
    return get_token()


def fetch_recent_corrections(limit: int = 100, since_days: int = 7) -> list:
    """Fetch recent ingredient_corrections from PocketBase."""
    headers = {"Authorization": f"Bearer {_get_token()}"}
    url = f"{PB_URL}/api/collections/ingredient_corrections/records?sort=-created&perPage={limit}"
    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
        if since_days:
            cutoff = (datetime.utcnow() - timedelta(days=since_days)).isoformat() + "Z"
            items = [c for c in items if (c.get("created") or "") >= cutoff]
        return items
    except Exception as e:
        print(f"⚠️ Failed to fetch corrections: {e}")
        return []


def build_summary_for_gpt(corrections: list) -> str:
    """Build a compact summary of corrections for GPT."""
    lines = []
    for c in corrections[:50]:  # cap to avoid token limit
        orig = c.get("originalParse", {}) or {}
        corr = c.get("userCorrection", {}) or {}
        reason = c.get("correctionReason") or "?"
        ctx = c.get("context", {}) or {}
        conv = ctx.get("conversation", []) or []
        # Get user message snippets
        user_msgs = [m.get("content", "")[:150] for m in conv if m.get("role") == "user"]
        summary = (
            f"- Original: {orig.get('name', '?')} ({orig.get('quantity', '?')} {orig.get('unit', '?')}) | "
            f"Corrected to: {corr.get('name', orig.get('name'))} ({corr.get('quantity')} {corr.get('unit')}) | "
            f"Reason: {reason}"
        )
        if user_msgs:
            summary += f" | User said: \"{user_msgs[0][:80]}...\"" if len(user_msgs[0]) > 80 else f" | User said: \"{user_msgs[0]}\""
        lines.append(summary)
    return "\n".join(lines)


def propose_rules_via_gpt(corrections_summary: str, existing_yaml: str) -> dict:
    """Call GPT to propose new rules based on corrections."""
    prompt = """You analyze user corrections to a meal logging app and propose updates to a deterministic rule file (common_sense_rules.yaml).
The rules fix things like: zero-calorie items showing calories, missing caffeine in tea/coffee, wrong portions, missing fiber.
When users repeatedly correct the same thing (e.g. "green tea should have caffeine"), that's a signal to add a rule.

Here are recent corrections:
{corrections}

Here is the CURRENT rule file (do not duplicate, only ADD new rules):
```yaml
{existing}
```

Output a JSON object with NEW rules only. Use the same structure:
{{
  "zero_calorie_patterns": ["pattern1", "pattern2"],
  "caffeine_mg_per_serving": {{ "ingredient": mg }},
  "portion_fixes": {{ "ingredient": {{ "quantity": 1, "unit": "serving", "serving_size_g": 50 }}}},
  "fiber_g_per_serving": {{ "ingredient": grams }},
  "added_sugar_g_per_serving": {{ "ingredient": grams }}
}}

Rules:
- Only propose rules that are UNIVERSALLY true (not user-specific, e.g. "I use oat milk").
- Skip anything already in the existing rules.
- If a correction was "misidentified" (wrong food) or "portion_estimate", consider if it suggests a rule.
- If users say "that should have caffeine" or "green tea has caffeine", add caffeine rule.
- Output ONLY valid JSON, no markdown."""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt.format(corrections=corrections_summary[:4000], existing=existing_yaml[:3000])}],
        max_tokens=1500,
    )
    raw = (resp.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def merge_proposed_into_rules(existing: dict, proposed: dict) -> dict:
    """Merge GPT-proposed rules into existing, deduplicating."""
    # Zero calorie
    zero = list(existing.get("zero_calorie", {}).get("patterns", []))
    for p in proposed.get("zero_calorie_patterns", []):
        if p and p.lower() not in [x.lower() for x in zero]:
            zero.append(p)
    existing["zero_calorie"] = {"patterns": zero}

    # Caffeine
    caf = dict(existing.get("caffeine_mg_per_serving", {}))
    for k, v in proposed.get("caffeine_mg_per_serving", {}).items():
        if k and k.lower() not in [x.lower() for x in caf]:
            caf[k] = v
    existing["caffeine_mg_per_serving"] = caf

    # Portion fixes
    port = dict(existing.get("portion_fixes", {}))
    for k, v in proposed.get("portion_fixes", {}).items():
        if k and isinstance(v, dict):
            port[k] = v
    existing["portion_fixes"] = port

    # Fiber
    fiber = dict(existing.get("fiber_g_per_serving", {}))
    for k, v in proposed.get("fiber_g_per_serving", {}).items():
        if k and k.lower() not in [x.lower() for x in fiber]:
            fiber[k] = v
    existing["fiber_g_per_serving"] = fiber

    # Added sugar
    sugar = dict(existing.get("added_sugar_g_per_serving", {}))
    for k, v in proposed.get("added_sugar_g_per_serving", {}).items():
        if k and k.lower() not in [x.lower() for x in sugar]:
            sugar[k] = v
    existing["added_sugar_g_per_serving"] = sugar

    return existing


def main():
    parser = argparse.ArgumentParser(description="Learn rules from corrections via GPT")
    parser.add_argument("--dry-run", action="store_true", help="Propose rules but don't write")
    parser.add_argument("--limit", type=int, default=80, help="Max corrections to fetch")
    parser.add_argument("--since-days", type=int, default=7, help="Only corrections from last N days")
    args = parser.parse_args()

    print("📡 Fetching recent corrections...")
    corrections = fetch_recent_corrections(limit=args.limit, since_days=args.since_days)
    if not corrections:
        print("   No corrections found. Nothing to learn.")
        return

    print(f"   Found {len(corrections)} corrections")
    summary = build_summary_for_gpt(corrections)
    existing_yaml = RULES_PATH.read_text() if RULES_PATH.exists() else ""
    if not existing_yaml:
        print("   No existing rules file. Creating from scratch.")
        existing = {}
    else:
        existing = yaml.safe_load(existing_yaml) or {}

    print("🤖 Asking GPT to propose new rules...")
    try:
        proposed = propose_rules_via_gpt(summary, existing_yaml)
    except Exception as e:
        print(f"   ❌ GPT failed: {e}")
        return

    # Count what's new
    added = 0
    for k, v in proposed.items():
        if isinstance(v, (list, dict)) and v:
            added += len(v)
    if added == 0:
        print("   No new rules proposed.")
        return

    merged = merge_proposed_into_rules(existing, proposed)
    yaml_str = yaml.dump(merged, default_flow_style=False, sort_keys=False, allow_unicode=True)
    header = """# Deterministic common-sense enrichment rules
# Applied at parse time BEFORE GPT common_sense_check
# Auto-updated by learn_rules_from_corrections.py (GPT learns from your corrections)

"""
    full = header + yaml_str

    if args.dry_run:
        print("=== DRY RUN - would write:")
        print(full[:1500] + "\n...")
        return

    RULES_PATH.write_text(full)
    print(f"✅ Updated {RULES_PATH}")
    print("   Restart parse API to pick up new rules.")


if __name__ == "__main__":
    main()
