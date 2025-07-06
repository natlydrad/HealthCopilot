//
//  MealLogManager.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import Foundation

class MealLogManager: ObservableObject {
    @Published var meals: [MealLog] = []
    
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
    }

