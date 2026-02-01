#!/usr/bin/env python3
"""Debug protein for a specific day."""
import os
import sys
from dotenv import load_dotenv
from pb_client import get_token, PB_URL
import requests

load_dotenv()

def debug_day(date_str: str):
    """Show protein breakdown for a specific day."""
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get meals for that day
    meals_url = f"{PB_URL}/api/collections/meals/records?perPage=200&filter=timestamp>='{date_str}'&filter=timestamp<'{date_str[:8]}{int(date_str[8:10])+1:02d}'"
    meals_resp = requests.get(meals_url, headers=headers)
    meals = meals_resp.json().get("items", [])
    
    print(f"\n=== {date_str} ===")
    print(f"Found {len(meals)} meals\n")
    
    # Get all ingredients
    ingredients_url = f"{PB_URL}/api/collections/ingredients/records?perPage=500"
    ingredients_resp = requests.get(ingredients_url, headers=headers)
    all_ings = ingredients_resp.json().get("items", [])
    
    UNIT_TO_GRAMS = {
        'oz': 28.35, 'g': 1, 'grams': 1, 'cup': 150, 'cups': 150,
        'piece': 50, 'pieces': 50, 'slice': 20, 'slices': 20,
        'serving': 100, 'eggs': 50, 'egg': 50, 'tbsp': 15, 'count': 50
    }
    
    day_ingredients = []
    meal_ids = {m['id'] for m in meals}
    
    for ing in all_ings:
        if ing.get('mealId') not in meal_ids:
            continue
        ts = (ing.get('timestamp') or '')[:10]
        if ts != date_str:
            continue
        
        nutrition = ing.get('nutrition', [])
        if not isinstance(nutrition, list) or not nutrition:
            continue
        
        protein_per_100g = 0
        for n in nutrition:
            name = (n.get('nutrientName') or '').lower()
            if name == 'protein':
                protein_per_100g = n.get('value', 0) or 0
        
        qty = ing.get('quantity', 1) or 1
        unit = (ing.get('unit') or 'serving').lower().strip()
        
        grams = qty * UNIT_TO_GRAMS.get(unit, 80)
        actual_protein = protein_per_100g * (grams / 100)
        
        day_ingredients.append({
            'name': ing['name'],
            'qty': qty,
            'unit': unit,
            'grams': grams,
            'protein_per_100g': protein_per_100g,
            'total_protein': actual_protein
        })
    
    day_ingredients.sort(key=lambda x: x['total_protein'], reverse=True)
    
    total_protein = sum(i['total_protein'] for i in day_ingredients)
    
    print(f"Total protein: {total_protein:.0f}g\n")
    print("Top contributors:")
    for ing in day_ingredients[:20]:
        if ing['total_protein'] > 5:
            print(f"  {ing['name']:30} {ing['qty']:4} {ing['unit']:8} = {ing['grams']:5.0f}g → {ing['total_protein']:5.0f}g P (per100g: {ing['protein_per_100g']:.1f}g)")

if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-01-30"
    debug_day(date)
