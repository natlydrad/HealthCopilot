#!/usr/bin/env python3
"""
Bootstrap common-sense rules using GPT. Expands common_sense_rules.yaml with additional
entries based on nutrition knowledge. Run once, review output, then merge into the main file.

Usage:
  python bootstrap_common_sense_rules.py [--dry-run] [--output rules_expanded.yaml]
"""

import os
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

RULES_PATH = Path(__file__).parent / "common_sense_rules.yaml"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def load_existing_rules() -> str:
    if RULES_PATH.exists():
        return RULES_PATH.read_text()
    return ""


def run_gpt_bootstrap(existing_yaml: str) -> dict:
    """Call GPT to generate additional rules in the same structure."""
    prompt = """You are helping build a deterministic nutrition rule set for a meal logging app.
The rules fix common mistakes: zero-calorie items showing calories, missing caffeine in tea/coffee,
wrong portions (e.g. matcha in oz instead of serving), missing fiber in whole grains, etc.

Here is the EXISTING rule set (YAML format):
```
{existing}
```

Generate ADDITIONAL rules to add. Output a JSON object with the same structure:

{{
  "zero_calorie_patterns": ["pattern1", "pattern2", ...],
  "caffeine_mg_per_serving": {{ "ingredient pattern": mg_per_serving, ... }},
  "portion_fixes": {{ "ingredient": {{ "quantity": 1, "unit": "serving", "serving_size_g": 50 }}, ... }},
  "fiber_g_per_serving": {{ "ingredient": grams, ... }},
  "added_sugar_g_per_serving": {{ "ingredient": grams, ... }}
}}

Rules:
- Only suggest rules that are UNIVERSALLY true (not user-specific or brand-specific).
- Use substring patterns that match ingredient names (case-insensitive).
- For caffeine: typical mg per 8oz cup or per serving. Green tea ~30, black tea ~47, coffee ~95, matcha ~70.
- For zero_calorie: things that have <5 cal typically (water, ice, plain tea, diet soda, broth).
- Skip anything already in the existing rules.
- Output ONLY valid JSON, no markdown."""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt.format(existing=existing_yaml[:4000])}],
        max_tokens=2000,
    )
    raw = (resp.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def merge_into_yaml(existing_path: Path, gpt_output: dict, output_path: Path, dry_run: bool):
    """Merge GPT output into YAML structure and write."""
    import yaml
    existing = {}
    if existing_path.exists():
        with open(existing_path) as f:
            existing = yaml.safe_load(f) or {}

    # Merge zero_calorie
    zero_pats = list(existing.get("zero_calorie", {}).get("patterns", []))
    for p in gpt_output.get("zero_calorie_patterns", []):
        if p and p.lower() not in [x.lower() for x in zero_pats]:
            zero_pats.append(p)
    existing["zero_calorie"] = {"patterns": zero_pats}

    # Merge caffeine
    caffeine = dict(existing.get("caffeine_mg_per_serving", {}))
    for k, v in gpt_output.get("caffeine_mg_per_serving", {}).items():
        if k and k.lower() not in [x.lower() for x in caffeine]:
            caffeine[k] = v
    existing["caffeine_mg_per_serving"] = caffeine

    # Merge portion_fixes
    portions = dict(existing.get("portion_fixes", {}))
    for k, v in gpt_output.get("portion_fixes", {}).items():
        if k and isinstance(v, dict):
            portions[k] = v
    existing["portion_fixes"] = portions

    # Merge fiber
    fiber = dict(existing.get("fiber_g_per_serving", {}))
    for k, v in gpt_output.get("fiber_g_per_serving", {}).items():
        if k and k.lower() not in [x.lower() for x in fiber]:
            fiber[k] = v
    existing["fiber_g_per_serving"] = fiber

    # Merge added_sugar
    sugar = dict(existing.get("added_sugar_g_per_serving", {}))
    for k, v in gpt_output.get("added_sugar_g_per_serving", {}).items():
        if k and k.lower() not in [x.lower() for x in sugar]:
            sugar[k] = v
    existing["added_sugar_g_per_serving"] = sugar

    yaml_str = yaml.dump(existing, default_flow_style=False, sort_keys=False, allow_unicode=True)
    header = """# Deterministic common-sense enrichment rules
# Applied at parse time BEFORE GPT common_sense_check
# Edit manually or run bootstrap_common_sense_rules.py to expand via GPT

"""
    full = header + yaml_str

    if dry_run:
        print("=== DRY RUN - would write to", output_path)
        print(full[:2000] + "\n...")
        return

    output_path.write_text(full)
    print(f"Wrote expanded rules to {output_path}")
    print("Review and merge into common_sense_rules.yaml if satisfied.")


def main():
    parser = argparse.ArgumentParser(description="Bootstrap common-sense rules via GPT")
    parser.add_argument("--dry-run", action="store_true", help="Print result, don't write")
    parser.add_argument("--output", default="common_sense_rules_expanded.yaml", help="Output file")
    args = parser.parse_args()

    existing = load_existing_rules()
    print("Loaded existing rules, calling GPT...")
    gpt_out = run_gpt_bootstrap(existing)
    print("GPT output keys:", list(gpt_out.keys()))
    output_path = Path(__file__).parent / args.output
    merge_into_yaml(RULES_PATH, gpt_out, output_path, args.dry_run)


if __name__ == "__main__":
    main()
