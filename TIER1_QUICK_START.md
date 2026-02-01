# Tier 1 Quick Start Guide

## Overview

This guide shows how to use the Tier 1 schema for user preferences and ingredient corrections.

---

## 1. User Preferences

### Create/Update User Preferences

```python
# Python example (for ML pipeline)
import requests

def create_user_preferences(user_id, token, preferences):
    url = f"{PB_URL}/api/collections/user_preferences/records"
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "user": user_id,
        "preferences": {
            "brands": preferences.get("brands", []),
            "portionMultipliers": preferences.get("portionMultipliers", {}),
            "preferredUnits": preferences.get("preferredUnits", {}),
            "dietaryRestrictions": preferences.get("dietaryRestrictions", []),
            "commonMeals": preferences.get("commonMeals", [])
        },
        "metadata": {
            "onboardingCompleted": True,
            "version": 1
        }
    }
    
    # Check if preferences exist
    existing = requests.get(
        f"{PB_URL}/api/collections/user_preferences/records?filter=(user='{user_id}')",
        headers=headers
    ).json()
    
    if existing.get("items"):
        # Update existing
        pref_id = existing["items"][0]["id"]
        r = requests.patch(
            f"{PB_URL}/api/collections/user_preferences/records/{pref_id}",
            headers=headers,
            json=payload
        )
    else:
        # Create new
        r = requests.post(url, headers=headers, json=payload)
    
    r.raise_for_status()
    return r.json()
```

### Get User Preferences

```python
def get_user_preferences(user_id, token):
    url = f"{PB_URL}/api/collections/user_preferences/records?filter=(user='{user_id}')"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    data = r.json()
    return data.get("items", [{}])[0] if data.get("items") else None
```

### Use Preferences in GPT Prompt

```python
def build_enhanced_prompt(text, user_preferences):
    """Enhance GPT prompt with user preferences."""
    base_prompt = """
    Extract foods, drinks, supplements from: "{text}".
    
    IMPORTANT: Decompose complex/composite foods into their base ingredients.
    """
    
    # Add user context
    if user_preferences:
        prefs = user_preferences.get("preferences", {})
        brands = prefs.get("brands", [])
        common_meals = prefs.get("commonMeals", [])
        
        context = ""
        if brands:
            context += f"\nUser frequently eats at: {', '.join(brands)}. "
            context += "When you see meals from these brands, use their standard portion sizes.\n"
        
        if common_meals:
            context += f"\nUser commonly eats: {', '.join(common_meals)}. "
            context += "Use similar ingredients/portions when parsing similar meals.\n"
        
        base_prompt += context
    
    return base_prompt.format(text=text)
```

---

## 2. Ingredient Corrections

### Create Correction

```python
def create_correction(ingredient_id, user_id, token, original_parse, user_correction):
    """Create an ingredient correction record."""
    url = f"{PB_URL}/api/collections/ingredient_corrections/records"
    headers = {"Authorization": f"Bearer {token}"}
    
    # Calculate multiplier
    original_qty = original_parse.get("quantity", 1)
    corrected_qty = user_correction.get("quantity", 1)
    multiplier = corrected_qty / original_qty if original_qty > 0 else 1.0
    
    # Determine correction type
    correction_type = "quantity_change"
    if original_parse.get("name") != user_correction.get("name"):
        correction_type = "name_change"
    elif original_parse.get("unit") != user_correction.get("unit"):
        correction_type = "unit_change"
    
    payload = {
        "ingredientId": ingredient_id,
        "user": user_id,
        "originalParse": original_parse,
        "userCorrection": user_correction,
        "multiplier": multiplier,
        "correctionType": correction_type
    }
    
    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()
    return r.json()
```

### Get User's Corrections (for learning)

```python
def get_user_corrections(user_id, token):
    """Get all corrections for a user (for Tier 2 learning)."""
    url = f"{PB_URL}/api/collections/ingredient_corrections/records"
    url += f"?filter=(user='{user_id}')&expand=ingredientId"
    headers = {"Authorization": f"Bearer {token}"}
    
    all_corrections = []
    page = 1
    per_page = 200
    
    while True:
        r = requests.get(f"{url}&page={page}&perPage={per_page}", headers=headers)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        all_corrections.extend(items)
        
        if len(items) < per_page:
            break
        page += 1
    
    return all_corrections
```

### Calculate Portion Multipliers (Tier 2 Preview)

```python
def calculate_portion_multipliers(user_id, token):
    """Calculate average multipliers per ingredient (Tier 2 learning)."""
    corrections = get_user_corrections(user_id, token)
    
    multipliers_by_ingredient = {}
    
    for corr in corrections:
        if corr.get("correctionType") != "quantity_change":
            continue
        
        original = corr.get("originalParse", {})
        ingredient_name = original.get("name", "").lower()
        
        if not ingredient_name:
            continue
        
        multiplier = corr.get("multiplier", 1.0)
        
        if ingredient_name not in multipliers_by_ingredient:
            multipliers_by_ingredient[ingredient_name] = []
        
        multipliers_by_ingredient[ingredient_name].append(multiplier)
    
    # Calculate averages
    avg_multipliers = {}
    for name, mults in multipliers_by_ingredient.items():
        if len(mults) >= 3:  # Need at least 3 corrections for reliability
            avg_multipliers[name] = sum(mults) / len(mults)
    
    return avg_multipliers
```

---

## 3. Frontend Integration (React/JavaScript)

### Fetch User Preferences

```javascript
// api.js
export async function fetchUserPreferences() {
  const token = localStorage.getItem("pb_token");
  const response = await fetch(
    `${PB_URL}/api/collections/user_preferences/records?filter=(user='${userId}')`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );
  const data = await response.json();
  return data.items?.[0] || null;
}

export async function saveUserPreferences(preferences) {
  const token = localStorage.getItem("pb_token");
  const existing = await fetchUserPreferences();
  
  const payload = {
    user: userId,
    preferences,
    metadata: {
      onboardingCompleted: true,
      version: 1,
    },
  };
  
  if (existing) {
    // Update
    const response = await fetch(
      `${PB_URL}/api/collections/user_preferences/records/${existing.id}`,
      {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }
    );
    return response.json();
  } else {
    // Create
    const response = await fetch(
      `${PB_URL}/api/collections/user_preferences/records`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }
    );
    return response.json();
  }
}
```

### Create Correction

```javascript
export async function correctIngredient(ingredientId, originalParse, userCorrection) {
  const token = localStorage.getItem("pb_token");
  
  // Calculate multiplier
  const originalQty = originalParse.quantity || 1;
  const correctedQty = userCorrection.quantity || 1;
  const multiplier = correctedQty / originalQty;
  
  // Determine correction type
  let correctionType = "quantity_change";
  if (originalParse.name !== userCorrection.name) {
    correctionType = "name_change";
  } else if (originalParse.unit !== userCorrection.unit) {
    correctionType = "unit_change";
  }
  
  const payload = {
    ingredientId,
    user: userId,
    originalParse,
    userCorrection,
    multiplier,
    correctionType,
  };
  
  const response = await fetch(
    `${PB_URL}/api/collections/ingredient_corrections/records`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
  
  return response.json();
}
```

---

## 4. Example Workflow

### Complete Flow: User Corrects Ingredient

```python
# 1. User logs meal
meal = {
    "text": "chicken salad",
    "timestamp": "2026-02-01T12:00:00Z"
}

# 2. GPT parses meal
ingredients = parse_ingredients(meal["text"])
# Returns: [{"name": "chicken", "quantity": 4, "unit": "oz", ...}]

# 3. Store ingredients
for ing in ingredients:
    ingredient_record = insert_ingredient({
        "mealId": meal["id"],
        "name": ing["name"],
        "quantity": ing["quantity"],
        "unit": ing["unit"],
        ...
    })

# 4. User sees ingredient and corrects it
original_parse = {
    "name": "chicken",
    "quantity": 4,
    "unit": "oz",
    "category": "food",
    "macros": {"calories": 180, "protein": 35, ...}
}

user_correction = {
    "name": "chicken",
    "quantity": 6,  # User corrects to 6oz
    "unit": "oz",
    "category": "food"
}

# 5. Create correction record
correction = create_correction(
    ingredient_id=ingredient_record["id"],
    user_id=user_id,
    token=token,
    original_parse=original_parse,
    user_correction=user_correction
)

# 6. Update ingredient with corrected values
update_ingredient(ingredient_record["id"], user_correction)

# 7. (Tier 2) Later, calculate multipliers
multipliers = calculate_portion_multipliers(user_id, token)
# Returns: {"chicken": 1.5, "rice": 0.8, ...}

# 8. (Tier 2) Update user preferences
update_preferences(user_id, {
    "portionMultipliers": multipliers
})
```

---

## 5. Migration Steps

### Step 1: Run Migrations

```bash
# In your PocketBase directory
./pocketbase migrate
```

Or if using PocketBase admin UI:
1. Go to Settings → Migrations
2. Upload migration files
3. Run migrations

### Step 2: Verify Collections Created

```python
# Check collections exist
collections = ["user_preferences", "ingredient_corrections"]
for coll in collections:
    r = requests.get(f"{PB_URL}/api/collections/{coll}/records?page=1&perPage=1")
    print(f"{coll}: {r.status_code}")
```

### Step 3: Test Basic Operations

```python
# Test create preferences
prefs = create_user_preferences(
    user_id="test_user",
    token=token,
    preferences={
        "brands": ["Chipotle"],
        "commonMeals": ["burrito bowl"]
    }
)
print("✅ Preferences created")

# Test create correction
correction = create_correction(
    ingredient_id="test_ing",
    user_id="test_user",
    token=token,
    original_parse={"name": "chicken", "quantity": 4, "unit": "oz"},
    user_correction={"name": "chicken", "quantity": 6, "unit": "oz"}
)
print("✅ Correction created")
```

---

## Next Steps

1. ✅ Run migrations
2. ✅ Test API endpoints
3. ✅ Build correction UI (frontend)
4. ✅ Update parser to use preferences
5. ✅ Build onboarding flow for preferences
6. ✅ Start collecting corrections (Tier 1 complete!)
7. 🔜 Build learning system (Tier 2)

---

## Troubleshooting

### Issue: "Collection not found"
- **Solution**: Make sure migrations ran successfully
- Check PocketBase logs for errors

### Issue: "User relation error"
- **Solution**: Ensure user ID exists in `users` collection
- Check that user is authenticated

### Issue: "Multiplier calculation wrong"
- **Solution**: Verify `originalParse.quantity` and `userCorrection.quantity` are numbers
- Handle division by zero (default to 1.0)

### Issue: "Preferences not updating"
- **Solution**: Check if preferences record exists (may need to create first)
- Verify user has update permissions

---

## Resources

- [Tier 1 Schema Design](./TIER1_SCHEMA_DESIGN.md)
- [MVP Tier Plan](./MVP_TIER_PLAN.md)
- [Implementation Strategy](./IMPLEMENTATION_STRATEGY.md)
