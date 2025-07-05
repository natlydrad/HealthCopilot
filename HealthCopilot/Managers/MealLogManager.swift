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
