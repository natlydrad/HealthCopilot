/**
 * Multi-framework food group tracking: MyPlate, Dr. Gregor's Daily Dozen, Longevity.
 * Each framework has different serving definitions. We map ingredients to servings
 * using keyword matching and quantity/unit conversion.
 */

const UNIT_TO_GRAMS = {
  oz: 28.35, g: 1, grams: 1, gram: 1, cup: 150, cups: 150,
  tbsp: 15, tablespoon: 15, tsp: 5, teaspoon: 5,
  piece: 50, pieces: 50, slice: 20, slices: 20, serving: 100,
  eggs: 50, egg: 50, pill: 0, pills: 0, capsule: 0, capsules: 0,
  l: 0, liter: 1000, ml: 1
};

// Keyword lists for classification
const BEANS = ['bean', 'beans', 'lentil', 'lentils', 'chickpea', 'chickpeas', 'hummus', 'edamame', 'tofu', 'tempeh', 'split pea', 'black bean', 'pinto', 'kidney', 'garbanzo'];
const BERRIES = ['berry', 'berries', 'strawberry', 'strawberries', 'blueberry', 'blueberries', 'raspberry', 'raspberries', 'blackberry', 'blackberries', 'cherry', 'cherries', 'cranberry', 'cranberries'];
const OTHER_FRUITS = ['apple', 'apples', 'banana', 'bananas', 'orange', 'oranges', 'grape', 'grapes', 'mango', 'mangoes', 'pineapple', 'pineapples', 'kiwi', 'kiwis', 'peach', 'peaches', 'pear', 'pears', 'plum', 'plums', 'melon', 'melons', 'watermelon', 'watermelons', 'cantaloupe', 'avocado', 'avocados', 'grapefruit'];
const CRUCIFEROUS = ['broccoli', 'brussels', 'cabbage', 'cauliflower', 'kale', 'bok choy', 'arugula', 'collard', 'mustard green', 'turnip', 'radish', 'watercress'];
const GREENS = ['lettuce', 'spinach', 'kale', 'arugula', 'chard', 'collard', 'mustard', 'turnip green', 'watercress', 'dandelion', 'endive', 'mesclun'];
const OTHER_VEG = ['carrot', 'carrots', 'tomato', 'tomatoes', 'cucumber', 'pepper', 'peppers', 'onion', 'garlic', 'celery', 'mushroom', 'zucchini', 'squash', 'eggplant', 'asparagus', 'green bean', 'beet', 'corn', 'pea', 'salsa', 'vegetable'];
const NUTS = ['nut', 'nuts', 'almond', 'almonds', 'walnut', 'walnuts', 'cashew', 'cashews', 'peanut', 'peanuts', 'pecan', 'pecans', 'pistachio', 'nut butter', 'almond butter', 'peanut butter'];
const WHOLE_GRAINS = ['oat', 'oats', 'oatmeal', 'quinoa', 'brown rice', 'barley', 'millet', 'bulgur', 'whole wheat', 'whole grain', 'focaccia', 'bread', 'toast', 'bagel', 'pita', 'tortilla', 'rice', 'pasta', 'noodle', 'cereal', 'cracker', 'muffin', 'pizza', 'crust'];
const GRAINS_ALL = [...WHOLE_GRAINS, 'flour', 'wheat', 'rye', 'couscous', 'wrap', 'bun', 'roll'];
const PROTEIN = ['chicken', 'beef', 'pork', 'turkey', 'lamb', 'fish', 'salmon', 'tuna', 'sardine', 'shrimp', 'crab', 'lobster', 'egg', 'meat', 'sausage', 'bacon', 'ham', 'burger', 'patty', 'wing', 'breast', 'thigh', 'steak', 'rib'];
const DAIRY = ['milk', 'cheese', 'yogurt', 'butter', 'cream', 'cottage cheese', 'greek yogurt', 'kefir'];

function toGrams(qty, unit) {
  const u = (unit || 'serving').toLowerCase();
  return qty * (UNIT_TO_GRAMS[u] ?? 80);
}

/**
 * Compute servings for MyPlate (USDA), Daily Dozen (Dr. Gregor), and Longevity frameworks.
 * @param {Array} ingredients - { name, quantity, unit, category, parsingMetadata }
 * @returns {Object} { myPlate, dailyDozen, longevity }
 */
export function computeServingsByFramework(ingredients) {
  const myPlate = { grains: 0, vegetables: 0, fruits: 0, protein: 0, dairy: 0 };
  const dailyDozen = { beans: 0, berries: 0, otherFruits: 0, cruciferous: 0, greens: 0, otherVeg: 0, flaxseed: 0, nuts: 0, spices: 0, wholeGrains: 0 };
  const longevity = { legumes: 0, wholeGrains: 0, vegetables: 0, fruits: 0, nuts: 0 }; // simplified

  for (const ing of ingredients) {
    const cat = ing.category || 'food';
    if (cat === 'supplement') continue;

    const name = (ing.name || '').toLowerCase();
    const qty = ing.quantity || 1;
    const unit = (ing.unit || '').toLowerCase();
    const grams = toGrams(qty, unit);

    // Prefer parsingMetadata foodGroupServings when available (GPT-estimated)
    const fg = ing.parsingMetadata?.foodGroupServings;
    if (fg && typeof fg === 'object' && cat !== 'supplement') {
      myPlate.grains += Number(fg.grains) || 0;
      myPlate.vegetables += Number(fg.vegetables) || 0;
      myPlate.fruits += Number(fg.fruits) || 0;
      myPlate.protein += Number(fg.protein) || 0;
      myPlate.dairy += Number(fg.dairy) || 0;
      // Map to Daily Dozen loosely: grains→wholeGrains, veg→greens+otherVeg, fruits→berries+otherFruits
      dailyDozen.wholeGrains += Number(fg.grains) || 0;
      dailyDozen.greens += (Number(fg.vegetables) || 0) * 0.5;
      dailyDozen.otherVeg += (Number(fg.vegetables) || 0) * 0.5;
      dailyDozen.berries += (Number(fg.fruits) || 0) * 0.3;
      dailyDozen.otherFruits += (Number(fg.fruits) || 0) * 0.7;
      dailyDozen.beans += Number(fg.protein) || 0; // rough: some protein is legumes
      longevity.legumes += (Number(fg.protein) || 0) * 0.3;
      longevity.wholeGrains += Number(fg.grains) || 0;
      longevity.vegetables += Number(fg.vegetables) || 0;
      longevity.fruits += Number(fg.fruits) || 0;
      continue;
    }

    // Keyword-based mapping
    if (BEANS.some(b => name.includes(b))) {
      if (unit === 'cup' || unit === 'cups') { dailyDozen.beans += qty * 2; longevity.legumes += qty * 2; myPlate.protein += qty * 4; }
      else if (unit === 'tbsp' || unit === 'tablespoon') { dailyDozen.beans += qty * 0.5; longevity.legumes += 0.25; myPlate.protein += 0.5; }
      else { dailyDozen.beans += grams / 120; longevity.legumes += grams / 120; myPlate.protein += grams / 28; }
    } else if (BERRIES.some(b => name.includes(b))) {
      if (unit === 'cup' || unit === 'cups') { dailyDozen.berries += qty * 2; myPlate.fruits += qty; longevity.fruits += qty; }
      else { dailyDozen.berries += grams / 75; myPlate.fruits += grams / 150; longevity.fruits += grams / 150; }
    } else if (OTHER_FRUITS.some(f => name.includes(f))) {
      if (unit === 'cup' || unit === 'cups') { dailyDozen.otherFruits += qty * 2; myPlate.fruits += qty; longevity.fruits += qty; }
      else if (unit === 'piece' || unit === 'pieces') { dailyDozen.otherFruits += qty; myPlate.fruits += qty * 0.5; longevity.fruits += qty * 0.5; }
      else { dailyDozen.otherFruits += grams / 120; myPlate.fruits += grams / 150; longevity.fruits += grams / 150; }
    } else if (CRUCIFEROUS.some(c => name.includes(c))) {
      if (unit === 'cup' || unit === 'cups') { dailyDozen.cruciferous += qty * 2; myPlate.vegetables += qty; longevity.vegetables += qty; }
      else { dailyDozen.cruciferous += grams / 90; myPlate.vegetables += grams / 150; longevity.vegetables += grams / 150; }
    } else if (GREENS.some(g => name.includes(g))) {
      if (unit === 'cup' || unit === 'cups') { dailyDozen.greens += qty * 2; myPlate.vegetables += qty; longevity.vegetables += qty; }
      else { dailyDozen.greens += grams / 50; myPlate.vegetables += grams / 150; longevity.vegetables += grams / 150; }
    } else if (OTHER_VEG.some(v => name.includes(v))) {
      if (unit === 'cup' || unit === 'cups') { dailyDozen.otherVeg += qty * 2; myPlate.vegetables += qty; longevity.vegetables += qty; }
      else if (unit === 'piece' || unit === 'pieces') { dailyDozen.otherVeg += qty; myPlate.vegetables += qty * 0.5; longevity.vegetables += qty * 0.5; }
      else { dailyDozen.otherVeg += grams / 90; myPlate.vegetables += grams / 150; longevity.vegetables += grams / 150; }
    } else if (NUTS.some(n => name.includes(n))) {
      if (unit === 'cup' || unit === 'cups') { dailyDozen.nuts += qty * 4; longevity.nuts += qty * 4; }
      else if (unit === 'tbsp' || unit === 'tablespoon') { dailyDozen.nuts += qty * 0.5; longevity.nuts += qty * 0.5; }
      else { dailyDozen.nuts += grams / 35; longevity.nuts += grams / 28; }
    } else if (name.includes('flax') || name.includes('chia')) {
      if (unit === 'tbsp' || unit === 'tablespoon') dailyDozen.flaxseed += qty;
      else dailyDozen.flaxseed += grams / 10;
    } else if (name.includes('turmeric') || name.includes('cumin') || name.includes('cinnamon') || name.includes('spice')) {
      dailyDozen.spices += 0.5; // rough
    } else if (GRAINS_ALL.some(g => name.includes(g))) {
      const isWhole = WHOLE_GRAINS.some(g => name.includes(g));
      if (unit === 'slice' || unit === 'slices') {
        myPlate.grains += qty;
        if (isWhole) { dailyDozen.wholeGrains += qty; longevity.wholeGrains += qty; }
      } else if (unit === 'piece' || unit === 'pieces') {
        myPlate.grains += qty;
        if (isWhole) { dailyDozen.wholeGrains += qty; longevity.wholeGrains += qty; }
      } else if (unit === 'cup' || unit === 'cups') {
        myPlate.grains += qty * 2;
        if (isWhole) { dailyDozen.wholeGrains += qty * 2; longevity.wholeGrains += qty * 2; }
      } else {
        const ozEq = grams / 28;
        myPlate.grains += ozEq;
        if (isWhole) { dailyDozen.wholeGrains += ozEq; longevity.wholeGrains += ozEq; }
      }
    } else if (PROTEIN.some(p => name.includes(p)) && !BEANS.some(b => name.includes(b))) {
      if (unit === 'oz') { myPlate.protein += qty; }
      else if (unit === 'egg' || unit === 'eggs') { myPlate.protein += qty; }
      else if (unit === 'cup' || unit === 'cups') { myPlate.protein += qty * 4; }
      else { myPlate.protein += grams / 28; }
    } else if (DAIRY.some(d => name.includes(d))) {
      if (unit === 'cup' || unit === 'cups') myPlate.dairy += qty;
      else if (unit === 'oz') myPlate.dairy += qty / 8;
      else myPlate.dairy += grams / 240;
    }
  }

  return { myPlate, dailyDozen, longevity };
}

/** MyPlate daily targets (2000 cal) - grains in oz-eq, veg/fruit in cups, protein in oz, dairy in cups */
export const MYPLATE_TARGETS = { grains: 6, vegetables: 2.5, fruits: 2, protein: 5.5, dairy: 3 };

/** Daily Dozen targets (Dr. Gregor) - servings per category */
export const DAILY_DOZEN_TARGETS = { beans: 3, berries: 1, otherFruits: 3, cruciferous: 1, greens: 2, otherVeg: 2, flaxseed: 1, nuts: 1, spices: 1, wholeGrains: 3 };

/** Longevity targets - plant-forward emphasis */
export const LONGEVITY_TARGETS = { legumes: 1.5, wholeGrains: 3, vegetables: 5, fruits: 2, nuts: 1 };
