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
        loadMeals()
        
        // ✅ TEMP: Add a fake March meal for glucose testing
        if meals.isEmpty {  // Only add if no meals exist
            print("📝 No meals found, adding fake meal")
            let fakeMeal = MealLog(
                description: "Fake March Meal",
                date: Calendar.current.date(from: DateComponents(year: 2025, month: 3, day: 25, hour: 12))!,
                calories: 300,
                protein: 20,
                carbs: 30,
                fat: 10
            )
            meals.append(fakeMeal)
            saveMeals()
        }
    }
        
        func addMeal(_ meal: MealLog) {
            meals.append(meal)
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
        
        private func loadMeals() {
            if let saved = UserDefaults.standard.data(forKey: storageKey),
               let decoded = try? JSONDecoder().decode([MealLog].self, from: saved) {
                meals = decoded
            }
        }
    
    func generateInsight(for meal: MealLog, using healthManager: HealthManager) {
        guard mealInsights[meal.id] == nil else { return }  // Already has insight

        let now = Date()
        let mealReadyTime = meal.date.addingTimeInterval(2 * 60 * 60)
        guard now >= mealReadyTime else {
            print("⏳ Meal is too recent—insight not ready yet for \(meal.description)")
            return
        }

        let mealStart = meal.date
        let mealEnd = Calendar.current.date(byAdding: .hour, value: 2, to: mealStart)!

        healthManager.fetchGlucoseData(startDate: mealStart.addingTimeInterval(-2 * 60 * 60), endDate: mealEnd) { glucoseSamples in
            if let spike = healthManager.analyzeGlucoseImpact(for: meal, glucoseData: glucoseSamples) {
                let recoveryMinutes = 75  // TODO: real recovery time
                let percentile = 50.0      // TODO: real percentile

                let insight = InsightGenerator.generateTags(for: spike, recoveryMinutes: recoveryMinutes, percentile: percentile)

                DispatchQueue.main.async {
                    self.mealInsights[meal.id] = insight
                }
            } else {
                DispatchQueue.main.async {
                    self.mealInsights[meal.id] = InsightGenerator.generateTags(for: 0, recoveryMinutes: 90, percentile: 50)
                }
            }
        }
    }

}

