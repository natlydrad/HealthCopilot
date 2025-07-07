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
                
            }
            
        }
    }
}
