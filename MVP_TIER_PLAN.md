# HealthCopilot MVP Tier Plan: Personalization & Communication Gap

## Executive Summary

This document outlines MVP tiers to bridge the communication gap between how users log meals and how GPT Vision interprets them, while building personalization capabilities for brands, portion sizes, and user preferences.

## Current State Analysis

### How Users Log Meals
- **Text input**: Free-form descriptions ("chicken salad", "burrito bowl")
- **Photo upload**: Images of meals (often with packaging, plates, context)
- **No structured data**: No brand info, portion sizes, or ingredient details

### How GPT Vision Currently Processes
- **Generic parsing**: Extracts ingredients with estimated portions
- **No personalization**: Uses average portion sizes (e.g., "chicken→4oz")
- **No brand awareness**: Matches to generic USDA foods
- **No learning**: Doesn't improve from user corrections

### The Communication Gap

| User Input | GPT Interpretation | Gap |
|------------|-------------------|-----|
| "chicken salad" | Generic chicken + lettuce + dressing | Missing: brand, portion size, specific ingredients |
| Photo of Chipotle bowl | Generic rice, beans, chicken, cheese | Missing: Chipotle-specific portions, brand nutrition data |
| "my usual breakfast" | Can't interpret | Missing: user history/preferences |
| "2 eggs" | 2 eggs × 50g = 100g | May be accurate, but no calibration |

## MVP Tiers

### **Tier 1: Foundation - Basic Personalization (Weeks 1-2)**

**Goal**: Capture user preferences and enable basic corrections

#### Features
1. **User Preferences Collection**
   - Onboarding flow: collect dietary preferences, common brands, typical portion sizes
   - Store in PocketBase `user_preferences` collection:
     ```json
     {
       "userId": "user123",
       "commonBrands": ["Chipotle", "Starbucks", "Whole Foods"],
       "portionSizeMultiplier": 1.0,  // Calibration factor
       "preferredUnits": {"meat": "oz", "grains": "cup"},
       "dietaryRestrictions": ["vegetarian"],
       "commonMeals": ["oatmeal", "chicken salad", "burrito bowl"]
     }
     ```

2. **Meal Correction UI**
   - Allow users to edit parsed ingredients
   - Add/remove ingredients
   - Adjust quantities
   - Store corrections in `ingredient_corrections` collection

3. **Enhanced GPT Prompts**
   - Include user's common brands in prompt context
   - Use user's typical portion sizes as hints
   - Example prompt enhancement:
     ```
     User typically eats Chipotle bowls. When you see a burrito bowl, 
     estimate portions based on Chipotle's standard sizes.
     ```

#### Technical Implementation
- **Database Schema**:
  - `user_preferences` table (PocketBase)
  - `ingredient_corrections` table (links to ingredients, stores user edits)
- **API Changes**:
  - `GET /api/user/preferences`
  - `POST /api/user/preferences`
  - `POST /api/ingredients/{id}/correct`
- **Parser Updates**:
  - Load user preferences before parsing
  - Pass preferences to GPT prompt

#### Success Metrics
- 50% of users complete onboarding preferences
- 20% of meals receive corrections
- Parsing accuracy improves by 15% for users with preferences

---

### **Tier 2: Learning System - Feedback Loop (Weeks 3-4)**

**Goal**: Learn from user corrections and improve parsing over time

#### Features
1. **Correction Tracking**
   - Track all user edits to ingredients
   - Store original GPT parse vs. user correction
   - Calculate accuracy metrics per ingredient type

2. **Personalized Portion Calibration**
   - Learn user's actual portion sizes vs. GPT estimates
   - Build per-user calibration multipliers:
     ```
     user_chicken_multiplier = avg(user_corrected_chicken / gpt_estimated_chicken)
     ```
   - Apply multipliers to future parses

3. **Brand-Specific Nutrition Database**
   - Curate nutrition data for common brands (Chipotle, Starbucks, etc.)
   - Store in `brand_foods` collection:
     ```json
     {
       "brand": "Chipotle",
       "item": "Chicken Burrito Bowl",
       "ingredients": [
         {"name": "chicken", "quantity": 4, "unit": "oz", "calories": 180},
         {"name": "rice", "quantity": 0.5, "unit": "cup", "calories": 130}
       ],
       "totalCalories": 650
     }
     ```
   - Prioritize brand matches when user mentions brand

4. **Smart Re-parsing**
   - When user corrects a meal, re-parse similar meals using learned patterns
   - Suggest corrections for past meals based on new learnings

#### Technical Implementation
- **New Collections**:
  - `brand_foods` (brand-specific nutrition data)
  - `parsing_accuracy` (track GPT accuracy per user/ingredient)
- **ML Pipeline**:
  - `learn_from_corrections.py`: Analyze corrections, build calibration models
  - `apply_personalization.py`: Apply learned multipliers to new parses
- **Parser Updates**:
  - Check brand database first before generic USDA lookup
  - Apply user-specific portion multipliers
  - Use correction history to improve prompts

#### Success Metrics
- Parsing accuracy improves 30% after 10 corrections
- 40% of meals match brand-specific data
- User corrections decrease by 25% over 2 weeks

---

### **Tier 3: Advanced Personalization - Context Awareness (Weeks 5-6)**

**Goal**: Understand user context and meal patterns

#### Features
1. **Meal Pattern Recognition**
   - Identify recurring meals ("my usual breakfast")
   - Store meal templates:
     ```json
     {
       "userId": "user123",
       "name": "My Usual Breakfast",
       "ingredients": [
         {"name": "oatmeal", "quantity": 0.5, "unit": "cup"},
         {"name": "banana", "quantity": 1, "unit": "piece"},
         {"name": "almond butter", "quantity": 1, "unit": "tbsp"}
       ],
       "frequency": "daily",
       "timeOfDay": "morning"
     }
     ```
   - Auto-fill when user logs "my usual breakfast"

2. **Context-Aware Parsing**
   - Use meal history to improve parsing:
     - "salad" → check last 5 salads user logged
     - Use most common ingredients/portions
   - Time-of-day patterns:
     - Breakfast items parsed differently than dinner items
   - Location context (if available):
     - "lunch" at Chipotle → use Chipotle menu

3. **Smart Suggestions**
   - Suggest ingredients based on:
     - What user usually eats at this time
     - What user ate yesterday (leftovers)
     - Common combinations in user's history

4. **Multi-Modal Input Enhancement**
   - Combine text + image more intelligently:
     - Text: "Chipotle bowl"
     - Image: Verify ingredients visible
     - Use text for brand/context, image for portion estimation

#### Technical Implementation
- **New Collections**:
  - `meal_templates` (user's recurring meals)
  - `meal_patterns` (learned patterns: time, location, combinations)
- **ML Pipeline**:
  - `pattern_recognition.py`: Identify recurring meals
  - `context_enhanced_parsing.py`: Use context to improve parsing
- **Parser Updates**:
  - Load user's meal templates
  - Use pattern matching for common meals
  - Enhance GPT prompts with context

#### Success Metrics
- 60% of users have at least 3 meal templates
- Parsing accuracy improves 20% using context
- 30% reduction in user corrections

---

### **Tier 4: Long-Term Optimization - Hybrid Approach (Weeks 7-8)**

**Goal**: Optimize for accuracy and cost while maintaining personalization

#### Features
1. **Hybrid Parsing Strategy**
   - **Rule-based first**: Check templates, brand DB, user history
   - **GPT Vision second**: Only for novel/unrecognized meals
   - **User confirmation**: Always allow quick correction
   
2. **Confidence Scoring**
   - Assign confidence scores to each parse:
     - High confidence (0.9+): Template match, brand DB match
     - Medium confidence (0.6-0.9): GPT parse with user history context
     - Low confidence (<0.6): Novel meal, require user confirmation
   
3. **Cost Optimization**
   - Cache GPT responses for similar meals
   - Batch process low-priority meals
   - Use cheaper models (gpt-4o-mini) for simple parses
   - Reserve GPT-4 Vision for complex/composite meals

4. **Continuous Learning**
   - Weekly retraining of personalization models
   - A/B testing of parsing strategies
   - User feedback loop for model improvement

#### Technical Implementation
- **Parsing Pipeline**:
  ```
  1. Check meal templates → if match, use template
  2. Check brand database → if match, use brand data
  3. Check user history → if similar meal found, use that
  4. GPT Vision → only if no matches
  5. User confirmation → always available
  ```
- **Cost Tracking**:
  - Monitor GPT API costs per user
  - Optimize prompts to reduce tokens
  - Cache frequently parsed meals

#### Success Metrics
- 70% of meals parsed without GPT (templates/brand DB)
- GPT API costs reduced by 50%
- Parsing accuracy maintained at 85%+

---

## Is GPT Vision Conducive to Long-Term Optimization?

### **Pros of Current GPT Vision Approach**
✅ **Flexibility**: Handles any meal, any cuisine, any presentation  
✅ **No manual curation**: Works out-of-the-box  
✅ **Rapid iteration**: Easy to improve prompts  
✅ **Multi-modal**: Can parse both text and images  

### **Cons of Current GPT Vision Approach**
❌ **Cost**: GPT-4 Vision is expensive (~$0.01-0.03 per image)  
❌ **Latency**: API calls add 2-5 seconds per meal  
❌ **Inconsistency**: Same meal may parse differently  
❌ **No learning**: Doesn't improve from user corrections  
❌ **Generic**: No personalization or brand awareness  

### **Recommended Hybrid Approach**

**Phase 1 (Tiers 1-2)**: Keep GPT Vision, add personalization layer
- Use GPT Vision as primary parser
- Add user preferences and corrections
- Build learning system on top

**Phase 2 (Tiers 3-4)**: Hybrid rule-based + GPT Vision
- Rule-based first (templates, brand DB, history)
- GPT Vision only for novel meals
- Continuous learning from corrections

**Phase 3 (Future)**: Consider alternatives
- **Fine-tuned vision model**: Train on user's corrected meals
- **Structured input**: Encourage users to log ingredients directly
- **Barcode scanning**: For packaged foods
- **Restaurant API integration**: Chipotle, Starbucks APIs

### **Alternative Approaches to Consider**

1. **Fine-Tuned Vision Model**
   - Train custom model on user's corrected meals
   - Lower cost per inference
   - Better personalization
   - Requires ML infrastructure

2. **Structured Input**
   - Encourage users to log ingredients directly
   - Use GPT only for suggestions/autocomplete
   - More accurate, less friction
   - May reduce user engagement

3. **Restaurant API Integration**
   - Integrate with Chipotle, Starbucks, etc. APIs
   - Pull nutrition data directly
   - Most accurate for chain restaurants
   - Limited to supported restaurants

4. **Barcode Scanning**
   - Scan barcodes for packaged foods
   - Use Open Food Facts or USDA database
   - Very accurate for packaged items
   - Doesn't work for prepared meals

## Implementation Roadmap

### **Immediate (Tier 1)**
- [ ] Design user preferences schema
- [ ] Build onboarding flow
- [ ] Add correction UI
- [ ] Enhance GPT prompts with preferences

### **Short-term (Tier 2)**
- [ ] Build correction tracking system
- [ ] Implement portion calibration
- [ ] Curate brand nutrition database
- [ ] Add learning pipeline

### **Medium-term (Tier 3)**
- [ ] Build meal template system
- [ ] Implement context-aware parsing
- [ ] Add pattern recognition
- [ ] Enhance multi-modal input

### **Long-term (Tier 4)**
- [ ] Implement hybrid parsing strategy
- [ ] Add confidence scoring
- [ ] Optimize costs
- [ ] Build continuous learning system

## Success Criteria

### **Tier 1 Success**
- ✅ 50% of users complete preferences
- ✅ 20% of meals receive corrections
- ✅ 15% accuracy improvement

### **Tier 2 Success**
- ✅ 30% accuracy improvement after 10 corrections
- ✅ 40% of meals use brand-specific data
- ✅ 25% reduction in corrections

### **Tier 3 Success**
- ✅ 60% of users have meal templates
- ✅ 20% accuracy improvement from context
- ✅ 30% reduction in corrections

### **Tier 4 Success**
- ✅ 70% of meals parsed without GPT
- ✅ 50% cost reduction
- ✅ 85%+ parsing accuracy maintained

## Conclusion

GPT Vision is a good starting point, but **not optimal for long-term personalization**. The recommended approach is a **hybrid system** that:

1. **Learns from users** (Tiers 1-2)
2. **Builds personalization** (Tier 3)
3. **Optimizes for cost and accuracy** (Tier 4)

This approach bridges the communication gap by:
- Understanding how users actually log meals
- Learning from corrections
- Building personalized models
- Reducing reliance on expensive GPT calls

The key insight: **Personalization requires learning from users, not just better prompts.**
