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
                    // ✅ Use real insight if available, fallback to placeholder
                    let insight = mealLogManager.mealInsights[meal.id] ?? InsightGenerator.generateTags(for: 0, recoveryMinutes: 90, percentile: 50)
                    
                    NavigationLink(
                        destination: MealInsightView(
                            meal: meal,
                            insight: insight,
                            averageSpike: 15
                        )
                    ) {
                        
                        MealRowView(meal: meal, insight: insight)
                    }
                    .onAppear {
                        mealLogManager.generateInsight(for: meal, using: healthManager)
                    }
                    
                }
                .onDelete { offsets in
                    for index in offsets {
                        if index < mealLogManager.meals.count {
                            let meal = mealLogManager.meals[index]
                            healthManager.deleteNutritionData(for: meal.date)  // optional: remove from HealthKit too
                        }
                    }
                    mealLogManager.deleteMeal(at: offsets)
                }
            .navigationTitle("Meal History")
                
            }
        }
    }
}
