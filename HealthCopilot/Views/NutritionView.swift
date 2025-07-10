//
//  NutritionView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI

struct NutritionView: View {
    @EnvironmentObject var mealLogManager: MealLogManager
    @EnvironmentObject var healthManager: HealthManager
    @State private var foodInput = ""
    @State private var gptResponse = "Nutrition breakdown will appear here."
    @State private var mealDate = Date()


    var body: some View {
        VStack(spacing: 20) {
            
            Text("What did you eat?")
                .font(.headline)
            
            DatePicker("Meal Time", selection: $mealDate, displayedComponents: [.date, .hourAndMinute])
                .padding()
            
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
            
            Button("📥 Load Test Meals") {
                mealLogManager.loadTestMeals()
            }
            .padding()
            

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
                    
                    let formatter = DateFormatter()
                    formatter.dateStyle = .short
                    formatter.timeStyle = .short

                    print("🕒 About to save with time: \(formatter.string(from: mealDate))")
                    
                    healthManager.saveNutritionToHealthKit(calories: nutrition.calories,
                                                           protein: nutrition.protein,
                                                           carbs: nutrition.carbs,
                                                           fat: nutrition.fat, date: mealDate)
                    
                    let meal = MealLog(description: self.foodInput,
                                                   date: mealDate,
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


