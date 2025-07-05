//
//  NutritionView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI

struct NutritionView: View {
    @StateObject var healthManager = HealthManager()
    @State private var foodInput = ""
    @State private var gptResponse = "Nutrition breakdown will appear here."
    @StateObject var mealLogManager = MealLogManager()


    var body: some View {
        VStack(spacing: 20) {
            Text("What did you eat?")
                .font(.headline)
            
            TextField("e.g., 2 eggs and toast", text: $foodInput)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .padding()

            Button("Analyze & Save to Health") {
                analyzeAndSaveFood()
            }
            .padding()

            Text(gptResponse)
                .padding()
                .multilineTextAlignment(.leading)
        }
        .padding()
        .onAppear {
            print("🔄 Loaded meals on startup: \(mealLogManager.meals.count)")
        }
    }

    func analyzeAndSaveFood() {
        let prompt = """
        I ate: \(foodInput)
        Please provide approximate totals:
        Calories (kcal)
        Protein (g)
        Carbs (g)
        Fat (g)
        
        Reply only like this:
        Calories: X kcal
        Protein: Y g
        Carbs: Z g
        Fat: W g
        """
        
        healthManager.fetchGPTSummary(prompt: prompt) { response in
            DispatchQueue.main.async {
                self.gptResponse = response ?? "No response."
                
                if let response = response,
                   let nutrition = healthManager.parseNutrition(from: response) {
                    
                    healthManager.saveNutritionToHealthKit(calories: nutrition.calories,
                                                           protein: nutrition.protein,
                                                           carbs: nutrition.carbs,
                                                           fat: nutrition.fat)
                    
                    let meal = MealLog(description: self.foodInput,
                                                   date: Date(),
                                                   calories: nutrition.calories,
                                                   protein: nutrition.protein,
                                                   carbs: nutrition.carbs,
                                                   fat: nutrition.fat)

                    mealLogManager.addMeal(meal)
                    print("✅ Meal saved: \(meal.description) at \(meal.date)")
                    print("📋 Total meals stored: \(mealLogManager.meals.count)")
                }
            }
        }
    }
}


