//
//  MealHistoryView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI


struct MealHistoryView: View {
    @StateObject var mealLogManager = MealLogManager()
    @StateObject var healthManager = HealthManager()
    
    var body: some View {
        NavigationView {
            List {
                ForEach(mealLogManager.meals) { meal in
                    VStack(alignment: .leading) {
                        Text(meal.description)
                            .font(.headline)
                        Text(meal.date, style: .date)
                            .font(.subheadline)
                        Text("Calories: \(Int(meal.calories)) kcal")
                            .font(.subheadline)
                    }
                }
                .onDelete { offsets in
                    for index in offsets {
                        if index < mealLogManager.meals.count {
                            let meal = mealLogManager.meals[index]
                            healthManager.deleteNutritionData(for: meal.date)  // ✅ Delete from HealthKit first
                        }
                    }

                    mealLogManager.deleteMeal(at: offsets)  // ✅ Then delete locally
                }
            }
            .navigationTitle("Meal History")
        }
    }
}
