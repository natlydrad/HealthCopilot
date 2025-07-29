//
//  HealthCopilotApp.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI

@main
struct HealthCopilotApp: App {
    @StateObject var mealLogManager = MealLogManager()
    @StateObject var healthManager = HealthManager()
    
    var body: some Scene {
        WindowGroup {
            TabView {
                PhotoMealLogger()
                    .tabItem {
                        Label("Photo", systemImage: "plus.circle")
                    }
                        
                        
                MealHistoryView()
                    .environmentObject(mealLogManager)
                    .environmentObject(healthManager)
                    .tabItem {
                        Label("History", systemImage: "list.bullet")
                    }
                                
                                /*
                                 NutritionView()
                                 .environmentObject(mealLogManager)
                                 .environmentObject(healthManager)
                                 .tabItem {
                                 Label("Log Meal", systemImage: "plus.circle")
                                 }
                                 
                                 GenInsightView()
                                 .environmentObject(mealLogManager)
                                 .environmentObject(healthManager)
                                 .tabItem {
                                 Label("Insights", systemImage: "list.bullet")
                                 }
                                 
                                 GlucoseScreen()
                                 .environmentObject(mealLogManager)
                                 .environmentObject(healthManager)
                                 .tabItem {
                                 Label("Glucose", systemImage: "waveform.path.ecg")
                                 }
                                 
                                 
                                 
                                 }
                                 */
                            }
                    }
            }
        }
