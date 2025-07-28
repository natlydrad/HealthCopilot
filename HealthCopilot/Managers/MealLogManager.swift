//
//  MealLogManager.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import Foundation

class MealLogManager: ObservableObject {
    @Published var meals: [MealLog] = []
    @Published var mealInsights: [UUID: MealInsight] = [:]
    
    
    private let storageKey = "MealLogs"
    
    init() {
        loadMealsFromCSV()
        
    }
    
    func addMeal(_ meal: MealLog) {
        var updatedMeals = meals
        updatedMeals.append(meal)
        meals = updatedMeals  // triggers SwiftUI update
        saveMeals()
    }
    
    func deleteMeal(at offsets: IndexSet) {
        meals.remove(atOffsets: offsets)
        saveMeals()
    }
    
    private func saveMeals() {
        if let encoded = try? JSONEncoder().encode(meals) {
            UserDefaults.standard.set(encoded, forKey: storageKey)
        }
    }
    
    func findNextMeal(after meal: MealLog) -> MealLog? {
        let sortedMeals = meals.sorted { $0.date < $1.date }
        guard let index = sortedMeals.firstIndex(where: { $0.id == meal.id }) else { return nil }
        let nextIndex = index + 1
        return nextIndex < sortedMeals.count ? sortedMeals[nextIndex] : nil
    }
    
    private func getMealsFileURL() -> URL {
        let manager = FileManager.default
        let url = manager.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return url.appendingPathComponent("meals.json")
    }
    
    
    func loadMealsFromCSV() {
        print("🌱 Loading meals from CSV...")

        guard let path = Bundle.main.path(forResource: "foodLogs_data", ofType: "csv") else {
            print("❌ CSV file not found.")
            return
        }

        do {
            let content = try String(contentsOfFile: path)
            let rows = content.components(separatedBy: .newlines).filter { !$0.isEmpty }

            guard let headerLine = rows.first else {
                print("❌ No header row found.")
                return
            }

            let headers = headerLine.components(separatedBy: ",")
            let dataRows = rows.dropFirst()

            var groupedIngredients: [String: [Ingredient]] = [:]
            var mealMeta: [String: (date: Date, name: String)] = [:]

            let dateFormatter = DateFormatter()
            dateFormatter.locale = Locale(identifier: "en_US_POSIX")
            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSX"


            for line in dataRows {
                let cols = line.components(separatedBy: ",")

                // Match the number of columns to your CSV (adjust if needed)
                guard cols.count >= 36 else { continue }

                let timestamp = cols[0]
                guard let date = dateFormatter.date(from: timestamp) else {
                    print("⚠️ Invalid date: \(timestamp)")
                    continue
                }

                let groupKey = timestamp
                let mealName = "Meal at \(date.formatted(date: .omitted, time: .shortened))"

                let ingredient = Ingredient(
                    name: cols[2],
                    unit: cols[3],
                    quantity: Double(cols[4]) ?? 0,
                    mass: Double(cols[5]) ?? 0,
                    calories: Double(cols[7]) ?? 0,
                    carbs: Double(cols[8]) ?? 0,
                    fat: Double(cols[9]) ?? 0,
                    protein: Double(cols[10]) ?? 0,
                    saturatedFat: Double(cols[11]),
                    transFat: Double(cols[12]),
                    monoFat: Double(cols[13]),
                    polyFat: Double(cols[14]),
                    cholesterol: Double(cols[15]),
                    sodium: Double(cols[16]),
                    fiber: Double(cols[17]),
                    sugar: Double(cols[18]),
                    sugarAdded: Double(cols[19]),
                    vitaminD: Double(cols[20]),
                    calcium: Double(cols[21]),
                    iron: Double(cols[22]),
                    potassium: Double(cols[23]),
                    vitaminA: Double(cols[24]),
                    vitaminC: Double(cols[25]),
                    alcohol: Double(cols[26]),
                    sugarAlcohol: Double(cols[27]),
                    vitaminB12: Double(cols[28]),
                    vitaminB12Added: Double(cols[29]),
                    vitaminB6: Double(cols[30]),
                    vitaminE: Double(cols[31]),
                    vitaminEAdded: Double(cols[32]),
                    magnesium: Double(cols[33]),
                    phosphorus: Double(cols[34]),
                    iodine: Double(cols[35])
                )

                groupedIngredients[groupKey, default: []].append(ingredient)
                mealMeta[groupKey] = (date: date, name: mealName)
            }

            let parsedMeals: [MealLog] = groupedIngredients.compactMap { key, ingredients in
                guard let meta = mealMeta[key] else { return nil }

                let totalCalories = ingredients.reduce(0) { $0 + $1.calories }
                let totalCarbs = ingredients.reduce(0) { $0 + $1.carbs }
                let totalFat = ingredients.reduce(0) { $0 + $1.fat }
                let totalProtein = ingredients.reduce(0) { $0 + $1.protein }
                

                return MealLog(
                    date: meta.date,
                    name: meta.name,
                    notes: nil,
                    ingredients: ingredients,
                    calories: totalCalories,
                    protein: totalProtein,
                    carbs: totalCarbs,
                    fat: totalFat,
                    spikeValue: nil,
                    auc: nil,
                    avgDelta: nil,
                    recoveryTime: nil,
                    responseScore: nil,
                    tags: []
                )
            }

            let sortedMeals = parsedMeals.sorted { $0.date > $1.date }

            DispatchQueue.main.async {
                self.meals.append(contentsOf: sortedMeals)
                self.saveMeals()
                print("✅ Loaded \(sortedMeals.count) meals from CSV (sorted by time 🕒)")
            }


        } catch {
            print("❌ Error reading CSV: \(error)")
        }
    }

}
