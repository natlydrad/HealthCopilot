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
const BEANS = ['bean', 'beans', 'lentil', 'lentils', 'chickpea', 'chickpeas', 'hummus', 'edamame', 'tofu', 'tempeh', 'soy', 'split pea', 'black bean', 'pinto', 'kidney', 'garbanzo'];
const BERRIES = ['berry', 'berries', 'strawberry', 'strawberries', 'blueberry', 'blueberries', 'raspberry', 'raspberries', 'blackberry', 'blackberries', 'cherry', 'cherries', 'cranberry', 'cranberries'];
const OTHER_FRUITS = ['apple', 'apples', 'banana', 'bananas', 'orange', 'oranges', 'grape', 'grapes', 'mango', 'mangoes', 'pineapple', 'pineapples', 'kiwi', 'kiwis', 'peach', 'peaches', 'pear', 'pears', 'plum', 'plums', 'melon', 'melons', 'watermelon', 'watermelons', 'cantaloupe', 'avocado', 'avocados', 'grapefruit'];
const CRUCIFEROUS = ['broccoli', 'brussels', 'cabbage', 'cauliflower', 'kale', 'bok choy', 'arugula', 'collard', 'mustard green', 'turnip', 'radish', 'watercress'];
const GREENS = ['lettuce', 'spinach', 'kale', 'arugula', 'chard', 'collard', 'mustard', 'turnip green', 'watercress', 'dandelion', 'endive', 'mesclun'];
const OTHER_VEG = ['carrot', 'carrots', 'tomato', 'tomatoes', 'marinara', 'pasta sauce', 'tomato sauce', 'cucumber', 'pepper', 'peppers', 'onion', 'garlic', 'celery', 'mushroom', 'zucchini', 'squash', 'eggplant', 'asparagus', 'green bean', 'beet', 'corn', 'pea', 'salsa', 'vegetable'];
const NUTS = ['nut', 'nuts', 'almond', 'almonds', 'walnut', 'walnuts', 'cashew', 'cashews', 'peanut', 'peanuts', 'pecan', 'pecans', 'pistachio', 'nut butter', 'almond butter', 'peanut butter'];
const WHOLE_GRAINS = ['oat', 'oats', 'oatmeal', 'quinoa', 'brown rice', 'barley', 'millet', 'bulgur', 'whole wheat', 'whole grain'];
const GRAINS_ALL = [...WHOLE_GRAINS, 'flour', 'wheat', 'rye', 'couscous', 'wrap', 'bun', 'roll', 'focaccia', 'bread', 'toast', 'bagel', 'pita', 'tortilla', 'rice', 'pasta', 'noodle', 'cereal', 'cracker', 'muffin', 'pizza', 'crust'];
const PROTEIN = ['chicken', 'beef', 'pork', 'turkey', 'lamb', 'fish', 'salmon', 'tuna', 'sardine', 'shrimp', 'crab', 'lobster', 'egg', 'meat', 'sausage', 'bacon', 'ham', 'burger', 'patty', 'wing', 'breast', 'thigh', 'steak', 'rib'];
const DAIRY = ['milk', 'cheese', 'yogurt', 'butter', 'cream', 'cottage cheese', 'greek yogurt', 'kefir'];

function toGrams(qty, unit) {
  const u = (unit || 'serving').toLowerCase();
  return qty * (UNIT_TO_GRAMS[u] ?? 80);
}

/** Return matched category from name only (for display/emoji when fg provides numbers) */
function matchedFromKeywords(name) {
  if (BEANS.some(b => name.includes(b))) return 'Beans/legumes';
  if (BERRIES.some(b => name.includes(b))) return 'Berries';
  if (OTHER_FRUITS.some(f => name.includes(f))) return 'Other fruits';
  if (CRUCIFEROUS.some(c => name.includes(c))) return 'Cruciferous';
  if (GREENS.some(g => name.includes(g))) return 'Greens';
  if (OTHER_VEG.some(v => name.includes(v))) return 'Other vegetables';
  if (NUTS.some(n => name.includes(n))) return 'Nuts';
  if (name.includes('flax') || name.includes('chia')) return 'Flaxseed/chia';
  if (name.includes('turmeric') || name.includes('cumin') || name.includes('cinnamon') || name.includes('spice')) return 'Spices';
  if (GRAINS_ALL.some(g => name.includes(g))) return WHOLE_GRAINS.some(g => name.includes(g)) ? 'Whole grains' : 'Grains';
  if (PROTEIN.some(p => name.includes(p)) && !BEANS.some(b => name.includes(b))) return 'Protein (animal)';
  if (DAIRY.some(d => name.includes(d))) return 'Dairy';
  return null;
}

/** Process one ingredient, return { mp, dd, lg, matched } — deltas and human-readable matched category */
function processIngredient(ing) {
  const mp = { grains: 0, vegetables: 0, fruits: 0, protein: 0, dairy: 0 };
  const dd = { beans: 0, berries: 0, otherFruits: 0, cruciferous: 0, greens: 0, otherVeg: 0, flaxseed: 0, nuts: 0, spices: 0, wholeGrains: 0 };
  const lg = { legumes: 0, wholeGrains: 0, vegetables: 0, fruits: 0, nuts: 0 };
  let matched = null;

  const cat = ing.category || 'food';
  if (cat === 'supplement') return { mp, dd, lg, matched: 'supplement (skipped)' };

  const name = (ing.name || '').toLowerCase();
  const qty = ing.quantity || 1;
  const unit = (ing.unit || '').toLowerCase();
  const grams = toGrams(qty, unit);

  const fg = ing.parsingMetadata?.foodGroupServings;
  if (fg && typeof fg === 'object') {
    const g = Number(fg.grains) || 0;
    const v = Number(fg.vegetables) || 0;
    const f = Number(fg.fruits) || 0;
    const p = Number(fg.protein) || 0;
    const d = Number(fg.dairy) || 0;
    const isLegumeSource = BEANS.some(x => name.includes(x));
    const isPlantMilk = isLegumeSource || /\b(almond|oat|coconut|cashew|rice)\s*milk\b/.test(name);
    const isBrothStock = /\b(broth|stock)\b/.test(name);
    mp.vegetables = v; mp.fruits = f;
    const baseProtein = isBrothStock ? 0 : (p + (isPlantMilk && d > 0 ? d : 0));
    mp.dairy = isPlantMilk ? 0 : d;

    const isWholeGrain = WHOLE_GRAINS.some(x => name.includes(x));
    const isGrainProduct = GRAINS_ALL.some(x => name.includes(x));
    let grainServings = g;
    if (isGrainProduct) {
      const est = unit === 'piece' || unit === 'pieces' ? qty : unit === 'slice' || unit === 'slices' ? qty : unit === 'cup' || unit === 'cups' ? qty * 2 : grams / 28;
      grainServings = Math.max(g, est);
    }
    mp.grains = grainServings;
    mp.protein = (isGrainProduct && !PROTEIN.some(x => name.includes(x)) && !BEANS.some(x => name.includes(x))) ? 0 : baseProtein;
    dd.wholeGrains = isWholeGrain ? grainServings : 0;
    lg.wholeGrains = isWholeGrain ? grainServings : 0;

    if (CRUCIFEROUS.some(x => name.includes(x))) {
      dd.cruciferous = v; dd.greens = 0; dd.otherVeg = 0;
    } else if (GREENS.some(x => name.includes(x))) {
      dd.cruciferous = 0; dd.greens = v; dd.otherVeg = 0;
    } else if (OTHER_VEG.some(x => name.includes(x))) {
      dd.cruciferous = 0; dd.greens = 0; dd.otherVeg = v;
    } else {
      dd.cruciferous = v * 0.25; dd.greens = v * 0.5; dd.otherVeg = v * 0.25;
    }
    lg.vegetables = v;

    if (BERRIES.some(x => name.includes(x))) {
      dd.berries = f; dd.otherFruits = 0;
    } else if (OTHER_FRUITS.some(x => name.includes(x))) {
      dd.berries = 0; dd.otherFruits = f;
    } else {
      dd.berries = f * 0.3; dd.otherFruits = f * 0.7;
    }
    lg.fruits = f;

    if (BEANS.some(x => name.includes(x))) {
      const beanP = p + (isLegumeSource && d > 0 ? d : 0);
      dd.beans = beanP; lg.legumes = beanP;
    } else if (PROTEIN.some(x => name.includes(x)) || isGrainProduct) {
      dd.beans = 0; lg.legumes = 0;
    } else if (isBrothStock) {
      dd.beans = 0; lg.legumes = 0;
    } else {
      dd.beans = p * 0.3; lg.legumes = p * 0.3;
    }

    matched = matchedFromKeywords(name) ?? 'GPT foodGroupServings';
    return { mp, dd, lg, matched };
  }

  if (BEANS.some(b => name.includes(b))) {
    if (unit === 'cup' || unit === 'cups') { dd.beans = qty * 2; lg.legumes = qty * 2; mp.protein = qty * 4; }
    else if (unit === 'tbsp' || unit === 'tablespoon') { dd.beans = qty * 0.5; lg.legumes = 0.25; mp.protein = 0.5; }
    else { dd.beans = grams / 120; lg.legumes = grams / 120; mp.protein = grams / 28; }
    matched = 'Beans/legumes';
  } else if (BERRIES.some(b => name.includes(b))) {
    if (unit === 'cup' || unit === 'cups') { dd.berries = qty * 2; mp.fruits = qty; lg.fruits = qty; }
    else { dd.berries = grams / 75; mp.fruits = grams / 150; lg.fruits = grams / 150; }
    matched = 'Berries';
  } else if (OTHER_FRUITS.some(f => name.includes(f))) {
    if (unit === 'cup' || unit === 'cups') { dd.otherFruits = qty * 2; mp.fruits = qty; lg.fruits = qty; }
    else if (unit === 'piece' || unit === 'pieces') { dd.otherFruits = qty; mp.fruits = qty * 0.5; lg.fruits = qty * 0.5; }
    else { dd.otherFruits = grams / 120; mp.fruits = grams / 150; lg.fruits = grams / 150; }
    matched = 'Other fruits';
  } else if (CRUCIFEROUS.some(c => name.includes(c))) {
    if (unit === 'cup' || unit === 'cups') { dd.cruciferous = qty * 2; mp.vegetables = qty; lg.vegetables = qty; }
    else { dd.cruciferous = grams / 90; mp.vegetables = grams / 150; lg.vegetables = grams / 150; }
    matched = 'Cruciferous';
  } else if (GREENS.some(g => name.includes(g))) {
    if (unit === 'cup' || unit === 'cups') { dd.greens = qty * 2; mp.vegetables = qty; lg.vegetables = qty; }
    else { dd.greens = grams / 50; mp.vegetables = grams / 150; lg.vegetables = grams / 150; }
    matched = 'Greens';
  } else if (OTHER_VEG.some(v => name.includes(v))) {
    if (unit === 'cup' || unit === 'cups') { dd.otherVeg = qty * 2; mp.vegetables = qty; lg.vegetables = qty; }
    else if (unit === 'piece' || unit === 'pieces') { dd.otherVeg = qty; mp.vegetables = qty * 0.5; lg.vegetables = qty * 0.5; }
    else { dd.otherVeg = grams / 90; mp.vegetables = grams / 150; lg.vegetables = grams / 150; }
    matched = 'Other vegetables';
  } else if (NUTS.some(n => name.includes(n))) {
    if (unit === 'cup' || unit === 'cups') { dd.nuts = qty * 4; lg.nuts = qty * 4; }
    else if (unit === 'tbsp' || unit === 'tablespoon') { dd.nuts = qty * 0.5; lg.nuts = qty * 0.5; }
    else { dd.nuts = grams / 35; lg.nuts = grams / 28; }
    matched = 'Nuts';
  } else if (name.includes('flax') || name.includes('chia')) {
    if (unit === 'tbsp' || unit === 'tablespoon') dd.flaxseed = qty;
    else dd.flaxseed = grams / 10;
    matched = 'Flaxseed/chia';
  } else if (name.includes('turmeric') || name.includes('cumin') || name.includes('cinnamon') || name.includes('spice')) {
    dd.spices = 0.5;
    matched = 'Spices';
  } else if (GRAINS_ALL.some(g => name.includes(g))) {
    const isWhole = WHOLE_GRAINS.some(g => name.includes(g));
    if (unit === 'slice' || unit === 'slices') { mp.grains = qty; if (isWhole) { dd.wholeGrains = qty; lg.wholeGrains = qty; } }
    else if (unit === 'piece' || unit === 'pieces') { mp.grains = qty; if (isWhole) { dd.wholeGrains = qty; lg.wholeGrains = qty; } }
    else if (unit === 'cup' || unit === 'cups') { mp.grains = qty * 2; if (isWhole) { dd.wholeGrains = qty * 2; lg.wholeGrains = qty * 2; } }
    else { const ozEq = grams / 28; mp.grains = ozEq; if (isWhole) { dd.wholeGrains = ozEq; lg.wholeGrains = ozEq; } }
    matched = isWhole ? 'Whole grains' : 'Grains';
  } else if (PROTEIN.some(p => name.includes(p)) && !BEANS.some(b => name.includes(b))) {
    if (unit === 'oz') mp.protein = qty;
    else if (unit === 'egg' || unit === 'eggs') mp.protein = qty;
    else if (unit === 'cup' || unit === 'cups') mp.protein = qty * 4;
    else mp.protein = grams / 28;
    matched = 'Protein (animal)';
  } else if (DAIRY.some(d => name.includes(d))) {
    if (unit === 'cup' || unit === 'cups') mp.dairy = qty;
    else if (unit === 'oz') mp.dairy = qty / 8;
    else mp.dairy = grams / 240;
    matched = 'Dairy';
  }

  return { mp, dd, lg, matched };
}

function sumObjs(acc, delta) {
  for (const k of Object.keys(delta)) {
    if (typeof delta[k] === 'number') acc[k] = (acc[k] || 0) + delta[k];
  }
}

/**
 * Compute servings for MyPlate, Daily Dozen, Longevity + per-ingredient attribution.
 * @returns {Object} { myPlate, dailyDozen, longevity, byIngredient, unmatched }
 */
export function computeServingsByFramework(ingredients) {
  const myPlate = { grains: 0, vegetables: 0, fruits: 0, protein: 0, dairy: 0 };
  const dailyDozen = { beans: 0, berries: 0, otherFruits: 0, cruciferous: 0, greens: 0, otherVeg: 0, flaxseed: 0, nuts: 0, spices: 0, wholeGrains: 0 };
  const longevity = { legumes: 0, wholeGrains: 0, vegetables: 0, fruits: 0, nuts: 0 };
  const byIngredient = [];
  const unmatched = [];

  for (const ing of ingredients) {
    const { mp, dd, lg, matched } = processIngredient(ing);
    sumObjs(myPlate, mp); sumObjs(dailyDozen, dd); sumObjs(longevity, lg);

    const contributed = Object.values(mp).some(v => v > 0) || Object.values(dd).some(v => v > 0) || Object.values(lg).some(v => v > 0);
    byIngredient.push({
      id: ing.id,
      name: ing.name || '?',
      quantity: ing.quantity ?? 1,
      unit: ing.unit || 'serving',
      myPlate: mp,
      dailyDozen: dd,
      longevity: lg,
      matched,
      contributed,
    });
    if (!contributed && matched !== 'supplement (skipped)') {
      unmatched.push({ name: ing.name || '?', quantity: ing.quantity ?? 1, unit: ing.unit || 'serving' });
    }
  }

  return { myPlate, dailyDozen, longevity, byIngredient, unmatched };
}

/** MyPlate daily targets (2000 cal) - grains in oz-eq, veg/fruit in cups, protein in oz, dairy in cups */
export const MYPLATE_TARGETS = { grains: 6, vegetables: 2.5, fruits: 2, protein: 5.5, dairy: 3 };

/** Daily Dozen targets (Dr. Gregor) - servings per category */
export const DAILY_DOZEN_TARGETS = { beans: 3, berries: 1, otherFruits: 3, cruciferous: 1, greens: 2, otherVeg: 2, flaxseed: 1, nuts: 1, spices: 1, wholeGrains: 3 };

/** Longevity targets - plant-forward emphasis */
export const LONGEVITY_TARGETS = { legumes: 1.5, wholeGrains: 3, vegetables: 5, fruits: 2, nuts: 1 };

/** Emoji for each matched category (for inline display next to ingredient) */
export const MATCHED_TO_EMOJI = {
  'Beans/legumes': '🫘',
  'Berries': '🫐',
  'Other fruits': '🍎',
  'Cruciferous': '🥦',
  'Greens': '🥬',
  'Other vegetables': '🥕',
  'Nuts': '🥜',
  'Flaxseed/chia': '🌾',
  'Spices': '🌿',
  'Whole grains': '🌾',
  'Grains': '🌾',
  'Protein (animal)': '🥩',
  'Dairy': '🥛',
  'GPT foodGroupServings': '🍽️',
};
