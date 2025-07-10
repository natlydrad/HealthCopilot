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
        
        private func loadMeals() {
            if let saved = UserDefaults.standard.data(forKey: storageKey),
               let decoded = try? JSONDecoder().decode([MealLog].self, from: saved) {
                meals = decoded
            }
        }
    
        func findNextMeal(after meal: MealLog) -> MealLog? {
            let sortedMeals = meals.sorted { $0.date < $1.date }
            guard let index = sortedMeals.firstIndex(where: { $0.id == meal.id }) else { return nil }
            let nextIndex = index + 1
            return nextIndex < sortedMeals.count ? sortedMeals[nextIndex] : nil
        }
    
        func calculateRecoveryTime(for meal: MealLog, glucoseData: [GlucoseSample], nextMeal: MealLog?) -> Double? {
            guard let preMealGlucose = glucoseData.last(where: { $0.date <= meal.date })?.value else {
                print("❌ No baseline glucose found for \(meal.description)")
                return nil
            }

            let recoveryThreshold: Double = 10  // mg/dL margin
            let baselineLow = preMealGlucose - recoveryThreshold
            let baselineHigh = preMealGlucose + recoveryThreshold

            let mealTime = meal.date
            let endTime = nextMeal?.date ?? mealTime.addingTimeInterval(4 * 60 * 60)  // ⏳ Extend window to 4h

            let postMealGlucose = glucoseData
                .filter { $0.date > mealTime && $0.date <= endTime }
                .sorted { $0.date < $1.date }

            var consecutiveInRangeCount = 0
            let requiredConsecutive = 3  // e.g., need 3 in-range readings in a row
            var firstRecoveryTime: Date?

            for sample in postMealGlucose {
                if sample.value >= baselineLow && sample.value <= baselineHigh {
                    consecutiveInRangeCount += 1
                    if consecutiveInRangeCount == 1 {
                        firstRecoveryTime = sample.date
                    }

                    if consecutiveInRangeCount >= requiredConsecutive, let recoveryDate = firstRecoveryTime {
                        let recoveryMinutes = recoveryDate.timeIntervalSince(mealTime) / 60
                        let minimumRecoveryMinutes = max(recoveryMinutes, 45)  // ⏳ Enforce minimum recovery time
                        return minimumRecoveryMinutes
                    }
                } else {
                    consecutiveInRangeCount = 0
                    firstRecoveryTime = nil
                }
            }

            return nil  // No stable recovery detected
        }


            
        func generateInsight(for meal: MealLog, using healthManager: HealthManager) {
            let now = Date()
            let mealReadyTime = meal.date.addingTimeInterval(2 * 60 * 60)
            
            guard now >= mealReadyTime else {
                print("⏳ Meal is too recent—insight not ready yet for \(meal.description)")
                return
            }
            
            if let existing = mealInsights[meal.id], existing.spikeValue != 0 {
                // 🛑 Skip recomputation if we already have a good spike
                return
            }
            
            let mealStart = meal.date
            let nextMeal = findNextMeal(after: meal)  // ✅ NEW: find the next meal
            let mealEnd = nextMeal?.date ?? Calendar.current.date(byAdding: .hour, value: 3, to: mealStart)!
            
            print("🔍 Generating insight for: \(meal.description) at \(mealStart)")
            if let next = nextMeal {
                print("➡️ Next meal: \(next.description) at \(next.date)")
            } else {
                print("➡️ No next meal—using default 3h window")
            }
            
            healthManager.fetchGlucoseData(startDate: mealStart.addingTimeInterval(-2 * 60 * 60), endDate: mealEnd) { glucoseSamples in
                
                guard let spike = healthManager.analyzeGlucoseImpact(for: meal, glucoseData: glucoseSamples) else {
                    print("⚠️ No spike detected for \(meal.description)")
                    DispatchQueue.main.async {
                        self.mealInsights[meal.id] = InsightGenerator.generateTags(for: 0, recoveryMinutes: 90, percentile: 50)
                    }
                    return
                }
                
                let recoveryMinutes = self.calculateRecoveryTime(for: meal, glucoseData: glucoseSamples, nextMeal: nextMeal) ?? 999  // ✅ NEW: real recovery time or placeholder
                print("✅ Spike: \(spike) mg/dL — Recovery: \(recoveryMinutes) min")
                
                let percentile = 50.0  // ✅ We’re skipping this for now
                
                let insight = InsightGenerator.generateTags(for: spike, recoveryMinutes: Int(recoveryMinutes), percentile: percentile)
                
                DispatchQueue.main.async {
                    self.mealInsights[meal.id] = insight
                }
            }
        }
        
        func loadTestMeals() {
            print("🌱 Loading test meals...")

            let testMeals: [MealLog] = [
                MealLog(
                    description: "1 rye bread, 2 eggs, 1/2 tbsp olive oil, 1/2 avocado, 1/4 cup georgian tomato sauce, 1 medium peach",
                    date: Calendar.current.date(from: DateComponents(year: 2025, month: 7, day: 7, hour: 8, minute: 25))!,
                    calories: 810,
                    protein: 35,
                    carbs: 60,
                    fat: 45
                ),
                MealLog(
                    description: "1 cup penne pasta, 60g white cabbage, 1 cup pork thighs, 120g chickpeas, 100g tomato sauce, 1 cup red grapes",
                    date: Calendar.current.date(from: DateComponents(year: 2025, month: 7, day: 7, hour: 14, minute: 50))!,
                    calories: 1178,
                    protein: 60,
                    carbs: 110,
                    fat: 50
                )
            ]

            meals.append(contentsOf: testMeals)
            saveMeals()
        }

        
    }
    
    

