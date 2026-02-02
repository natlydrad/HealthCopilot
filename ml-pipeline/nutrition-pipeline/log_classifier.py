"""
Log Entry Classifier
Classifies raw log entries into categories:
- food: meals, snacks, caloric beverages
- hydration: water intake tracking
- poop: bowel movements
- mood: emotions, feelings
- symptom: physical symptoms
- supplement: vitamins, supplements
- medication: drugs, medicine
- activity: exercise, sleep, activities

Mixed entries (e.g., "ate chicken and felt nauseous") get:
- isFood=True (so food part gets parsed)
- categories=["food", "symptom"]
- Food portion → ingredients table
- Non-food portions → non_food_logs table
"""

import os
import json
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# PocketBase config
PB_URL = os.getenv("PB_URL") or "http://127.0.0.1:8090"
PB_EMAIL = os.getenv("PB_EMAIL")
PB_PASSWORD = os.getenv("PB_PASSWORD")

CLASSIFICATION_PROMPT = """You are a health log classifier. Analyze the user's log entry and classify it.

Categories:
- food: Eating food, meals, snacks, beverages with calories (coffee, matcha, smoothies)
- hydration: Water intake tracking (start/finish water bottle, plain water) - NOT drinks with calories
- poop: Bowel movements, bathroom, stool descriptions
- mood: Emotions, feelings, mental state (happy, sad, anxious, stressed, crying)
- symptom: Physical symptoms (nausea, headache, pain, tired, fatigue)
- supplement: Vitamins, supplements (vitamin D, fish oil, magnesium, etc.)
- medication: Drugs, medicine, OTC meds (naproxen, ibuprofen, tylenol, etc.)
- activity: Exercise, sleep, activities, events
- other: Doesn't fit above categories

IMPORTANT: An entry can have MULTIPLE categories. For example:
- "ate chicken and felt nauseous" = food + symptom
- "finished water bottle, small poop" = hydration + poop
- "coffee with milk" = food (because it has calories/nutritional content)
- "started my 40oz water bottle" = hydration (just tracking water intake, no calories)
- "220mg naproxen" = medication (it's a drug)
- "vitamin D 2000IU" = supplement (vitamins are supplements, not food)
- "fish oil capsule" = supplement

Return JSON with:
{
  "categories": ["food", "symptom"],  // all that apply
  "primary": "food",  // the main category
  "food_portion": "ate chicken",  // if food, extract the food part
  "non_food_portions": {
    "symptom": "felt nauseous"
  },
  "confidence": 0.95,
  "reasoning": "Entry mentions eating chicken (food) and feeling nauseous (symptom)"
}

If it's ONLY food, non_food_portions should be empty {}.
If it's ONLY non-food, food_portion should be null.
"""

CLASSIFICATION_WITH_IMAGE_PROMPT = """You are a health log classifier. Analyze the user's log entry.

You are given:
1. An optional caption/text (e.g. "1 serving", "lunch", or empty)
2. An image (photo of what was logged)

Classify the ENTIRE entry (image + text together) using the same categories as text-only classification.

Categories:
- food: Eating food, meals, snacks, beverages with calories (coffee, matcha, smoothies). The image shows actual food/drink to log.
- hydration: Water intake (plain water, water bottle) - NOT drinks with calories
- poop: Bowel movements, stool descriptions
- mood: Emotions, feelings
- symptom: Physical symptoms
- supplement: Vitamins, supplements (pills, capsules, gummies)
- medication: Drugs, medicine, OTC meds
- activity: Exercise, sleep, activities
- other: Doesn't fit above (e.g. photo of a pill bottle, screenshot, non-food item)

CRITICAL: Use the IMAGE to decide. If the image shows a meal, plate of food, drink with calories, or edible items → include "food".
If the image shows only medication, supplements, a water bottle (hydration), or non-food (e.g. rug, receipt) → do NOT include "food".
Do not put non-food items (medication, supplements, hydration-only) into ingredients; classify them correctly so we do not parse them as food.

Return the same JSON format:
{
  "categories": ["food"] or ["supplement"] or ["medication"] etc,
  "primary": "food" or the main category,
  "food_portion": "description of food" if food, else null,
  "non_food_portions": { "category": "content" } for non-food parts,
  "confidence": 0.95,
  "reasoning": "Brief explanation using both image and text"
}
"""


def classify_log(entry_text: str, verbose: bool = False) -> dict:
    """
    Classify a raw log entry.
    
    Returns:
        {
            "categories": ["food", "symptom"],
            "primary": "food",
            "food_portion": "chicken salad",
            "non_food_portions": {"symptom": "felt tired"},
            "confidence": 0.95,
            "reasoning": "..."
        }
    """
    if not entry_text or not entry_text.strip():
        return {
            "categories": ["other"],
            "primary": "other",
            "food_portion": None,
            "non_food_portions": {},
            "confidence": 1.0,
            "reasoning": "Empty entry"
        }
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {"role": "user", "content": f"Classify this log entry:\n\n{entry_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        result = json.loads(response.choices[0].message.content)
        
        if verbose:
            print(f"Entry: {entry_text[:60]}...")
            print(f"Categories: {result.get('categories')}")
            print(f"Reasoning: {result.get('reasoning')}")
            print()
        
        return result
        
    except Exception as e:
        print(f"Error classifying: {e}")
        return {
            "categories": ["other"],
            "primary": "other",
            "food_portion": None,
            "non_food_portions": {},
            "confidence": 0.0,
            "reasoning": f"Error: {str(e)}"
        }


def classify_log_with_image(entry_text: str, meal: dict, pb_url: str, token: str | None = None, verbose: bool = False) -> dict:
    """
    Classify a log entry using both optional text and image.
    Use this when the meal has an image so classification considers the photo (e.g. food vs medication vs supplement).
    Falls back to text-only classify_log when no image is available.
    Returns same shape as classify_log().
    """
    from parser_gpt import get_image_base64

    image_b64 = get_image_base64(meal, pb_url, token) if meal else None

    if not image_b64:
        return classify_log(entry_text or "", verbose=verbose)

    text_part = (entry_text or "").strip()
    user_content = [
        {"type": "text", "text": f"Classify this log entry. Caption/text: \"{text_part or '(none)'}\"\n\nUse the image to decide. Same JSON format as text-only classification."},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CLASSIFICATION_WITH_IMAGE_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        result = json.loads(response.choices[0].message.content)
        if verbose:
            print(f"Classify (text+image): categories={result.get('categories')}")
        return result
    except Exception as e:
        print(f"Error classifying with image: {e}")
        return classify_log(entry_text or "", verbose=verbose)


def classify_batch(entries: list, verbose: bool = False) -> list:
    """Classify multiple entries."""
    results = []
    for entry in entries:
        result = classify_log(entry, verbose=verbose)
        result["original_text"] = entry
        results.append(result)
    return results


# ============================================================
# Interactive Testing Mode
# ============================================================

def test_one_by_one(entries: list):
    """
    Interactive testing mode - classify one entry at a time,
    show result, and let user confirm or correct.
    """
    corrections = []
    
    for i, entry in enumerate(entries):
        print(f"\n{'='*60}")
        print(f"Entry {i+1}/{len(entries)}")
        print(f"{'='*60}")
        print(f"\n📝 {entry}\n")
        
        result = classify_log(entry)
        
        print(f"🏷️  Categories: {result.get('categories')}")
        print(f"📌 Primary: {result.get('primary')}")
        if result.get('food_portion'):
            print(f"🍽️  Food part: {result.get('food_portion')}")
        if result.get('non_food_portions'):
            print(f"📋 Non-food parts: {result.get('non_food_portions')}")
        print(f"💭 Reasoning: {result.get('reasoning')}")
        
        # Get user feedback
        print("\n[Enter] = correct, [c] = correct it, [s] = skip, [q] = quit")
        choice = input("> ").strip().lower()
        
        if choice == 'q':
            break
        elif choice == 's':
            continue
        elif choice == 'c':
            print("What should the categories be? (comma-separated: food,symptom)")
            new_cats = input("> ").strip().split(',')
            new_cats = [c.strip() for c in new_cats if c.strip()]
            
            corrections.append({
                "text": entry,
                "original_classification": result,
                "corrected_categories": new_cats
            })
            print(f"✅ Recorded correction: {new_cats}")
        else:
            print("✅ Classification confirmed")
    
    return corrections


# ============================================================
# PocketBase Integration
# ============================================================

from pb_client import get_token

def update_meal_classification(meal_id: str, is_food: bool, categories: list):
    """
    Update a meal record with classification results.
    """
    url = f"{PB_URL}/api/collections/meals/records/{meal_id}"
    headers = {"Authorization": f"Bearer {get_token()}"}
    
    data = {
        "isFood": is_food,
        "categories": categories
    }
    
    try:
        r = requests.patch(url, headers=headers, json=data)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error updating meal {meal_id}: {e}")
        return None


def insert_non_food_log(meal_id: str, user_id: str, category: str, content: str, timestamp: str, metadata: dict = None):
    """
    Insert a non-food log entry.
    """
    url = f"{PB_URL}/api/collections/non_food_logs/records"
    headers = {"Authorization": f"Bearer {get_token()}"}
    
    data = {
        "mealId": meal_id,
        "user": user_id,
        "category": category,
        "content": content,
        "timestamp": timestamp,
        "metadata": metadata or {}
    }
    
    try:
        r = requests.post(url, headers=headers, json=data)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error inserting non_food_log: {e}")
        return None


def process_and_save_classification(meal: dict, verbose: bool = False):
    """
    Classify a meal and save results to PocketBase.
    
    Returns:
        {
            "meal_id": "abc123",
            "is_food": True,
            "categories": ["food", "symptom"],
            "non_food_logs_created": 1
        }
    """
    meal_id = meal.get("id")
    text = meal.get("text", "")
    user_id = meal.get("user")
    timestamp = meal.get("timestamp")
    
    if not text:
        return {"meal_id": meal_id, "is_food": False, "categories": ["other"], "skipped": True}
    
    # Classify
    result = classify_log(text, verbose=verbose)
    categories = result.get("categories", ["other"])
    is_food = "food" in categories
    
    # Update meal with classification
    update_meal_classification(meal_id, is_food, categories)
    
    # Create non_food_logs for non-food categories
    non_food_count = 0
    non_food_portions = result.get("non_food_portions", {})
    
    for cat in categories:
        if cat != "food" and cat != "other":
            content = non_food_portions.get(cat, text)  # Use extracted portion or full text
            insert_non_food_log(meal_id, user_id, cat, content, timestamp)
            non_food_count += 1
    
    return {
        "meal_id": meal_id,
        "text": text[:50],
        "is_food": is_food,
        "categories": categories,
        "non_food_logs_created": non_food_count
    }


def classify_all_meals(limit: int = None, verbose: bool = False):
    """
    Classify all unclassified meals.
    """
    from pb_client import fetch_meals
    
    meals = fetch_meals()
    
    # Filter to unclassified (isFood is null)
    unclassified = [m for m in meals if m.get("isFood") is None]
    
    if limit:
        unclassified = unclassified[:limit]
    
    print(f"📊 Found {len(unclassified)} unclassified meals")
    
    results = {"food": 0, "non_food": 0, "mixed": 0, "errors": 0}
    
    for i, meal in enumerate(unclassified):
        try:
            r = process_and_save_classification(meal, verbose=verbose)
            
            if r.get("skipped"):
                continue
            
            cats = r.get("categories", [])
            if "food" in cats and len(cats) > 1:
                results["mixed"] += 1
            elif "food" in cats:
                results["food"] += 1
            else:
                results["non_food"] += 1
                
            if verbose:
                print(f"[{i+1}/{len(unclassified)}] {r}")
                
        except Exception as e:
            results["errors"] += 1
            print(f"Error processing meal: {e}")
    
    print(f"\n✅ Classification complete: {results}")
    return results


if __name__ == "__main__":
    # Quick test
    test_entries = [
        "miss saigon pho beef and tripe no noodles",
        "start hot 40oz salt water bottle",
        "soft poop closer to liquid",
        "cried from joy — sugar the cat sits in the room",
        "i feel tired. i have been keeping busy",
        "1.5 eggs scrambled (got so nauseous and couldn't finish)",
        "urgent poop; also halfway thru the coffee",
        "220mg naproxen sodium",
        "finished matcha",
        "salmon fillet, 6 strawberries",
    ]
    
    print("🧪 Testing classifier on sample entries...\n")
    
    for entry in test_entries:
        result = classify_log(entry, verbose=True)
