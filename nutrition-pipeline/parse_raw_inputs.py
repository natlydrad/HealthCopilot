# nutrition-pipeline/parse_raw_inputs.py
import json, datetime, requests
from pb_client import fetch_records, patch_record, PB_URL
from parser_gpt import parse_ingredients  # current parser extracts foods

RAW = "raw_inputs"

def iso_now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def should_parse(rec):
    """
    Parse if:
      - status is 'pending'  AND
      - (no parsed_at) OR (rec['updated'] > parsed_at)
    """
    status = rec.get("status")
    if status != "pending":
        return False
    parsed_at = rec.get("parsed_at")
    updated = rec.get("updated")  # system field from PB
    if not parsed_at:
        return True
    try:
        pa = datetime.datetime.fromisoformat(parsed_at.replace("Z","+00:00"))
        up = datetime.datetime.fromisoformat(updated.replace("Z","+00:00"))
        return up > pa
    except Exception:
        # if weird dates, be conservative and allow parse
        return True

def main():
    raws = fetch_records(RAW, "status='pending'")
    print(f"🧾 Found {len(raws)} pending raw_inputs")

    for rec in raws:
        # Only (re)parse if user edited after last parse
        if not should_parse(rec):
            print(f"⏭️ Skip (already parsed & unchanged): {rec.get('id')}")
            continue

        text = rec.get("text","")
        print(f"\n🟩 Parsing: {text[:60]}...")

        try:
            entities = parse_ingredients(text)  # CURRENTLY food-only
            print(f"✅ Parsed → {entities}")

            patch_record(RAW, rec["id"], {
                "status": "parsed",
                "parsed": entities,
                "parsed_at": iso_now()
            })
        except Exception as e:
            print(f"⚠️ Error: {e}")
            patch_record(RAW, rec["id"], {
                "status": "error",
                "parsed": {"error": str(e)}
            })

if __name__ == "__main__":
    main()
