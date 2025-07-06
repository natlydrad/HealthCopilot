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


                
                
                
                
                
                
                
                
                
                
                
                /*
                 ForEach(mealLogManager.meals) { meal in
                 NavigationLink(
                 destination: MealInsightView(
                 meal: meal,
                 insight: InsightGenerator.generateTags(
                 for: meal.spikeValue ?? 0,
                 recoveryMinutes: Int(meal.recoveryTime ?? 90),
                 percentile: 50  // ✅ TEMP: Replace with real value later
                 ),
                 averageSpike: 15  // Fake 7-day average for now (you can replace this later)
                 //averageSpike: calculateSevenDayAverage(meals: mealLogManager.meals)
                 )
                 ) {
                 VStack(alignment: .leading) {
                 Text(meal.description)
                 .font(.headline)
                 Text(meal.date, style: .date)
                 .font(.subheadline)
                 Text(meal.date, style: .time)
                 .font(.subheadline)
                 Text("Calories: \(Int(meal.calories)) kcal")
                 .font(.subheadline)
                 }
                 }
                 }
                 .onDelete { offsets in
                 for index in offsets {
                 if index < mealLogManager.meals.count {
                 let meal = mealLogManager.meals[index]
                 healthManager.deleteNutritionData(for: meal.date)
                 }
                 }
                 mealLogManager.deleteMeal(at: offsets)
                 }
                 }
                 .navigationTitle("Meal History")*/
     
