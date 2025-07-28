//
//  MealHistoryView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI


struct MealHistoryView: View {
    @EnvironmentObject var mealLogManager: MealLogManager
    @EnvironmentObject var healthManager: HealthManager
    
    var body: some View {
        NavigationView {
            List {
                ForEach(mealLogManager.meals, id: \.id) { meal in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(meal.name)
                            .font(.headline)
                        Text(meal.date.formatted(date: .abbreviated, time: .shortened))
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                        Text("Calories: \(Int(meal.calories)) • Protein: \(Int(meal.protein))g • Carbs: \(Int(meal.carbs))g • Fat: \(Int(meal.fat))g")
                            .font(.caption)
                    }
                    .padding(.vertical, 4)

                }
            .navigationTitle("Meal History")
                
            }
        }
    }
}
