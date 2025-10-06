import json
from pb_client import fetch_records, patch_record, PB_URL
from parser_gpt import parse_ingredients  # uses GPT to classify logs

RAW = "raw_inputs"

def main():
    raws = fetch_records(RAW, "status='pending'")
    print(f"🧾 Found {len(raws)} pending raw_inputs")

    for rec in raws:
        text = rec["text"]
        print(f"\n🟩 Parsing: {text[:50]}...")

        try:
            entities = parse_ingredients(text)
            print(f"✅ Parsed → {entities}")
            patch_record(RAW, rec["id"], {
                "status": "parsed",
                "parsed": entities
            })
        except Exception as e:
            print(f"⚠️ Error: {e}")
            patch_record(RAW, rec["id"], {
                "status": "error",
                "parsed": {"error": str(e)}
            })

if __name__ == "__main__":
    main()
