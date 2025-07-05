//
//  MealHistoryView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI

struct MealHistoryView: View {
    @StateObject var mealLogManager = MealLogManager()

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
                .onDelete(perform: mealLogManager.deleteMeal)
            }
            .navigationTitle("Meal History")
        }
    }
}
