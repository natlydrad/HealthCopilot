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
                NutritionView()
                    .environmentObject(mealLogManager)
                    .environmentObject(healthManager)
                    .tabItem {
                        Label("Log Meal", systemImage: "plus.circle")
                    }

                MealHistoryView()
                    .environmentObject(mealLogManager)
                    .environmentObject(healthManager)
                    .tabItem {
                        Label("History", systemImage: "list.bullet")
                    }
                
                GlucoseScreen()
                    .environmentObject(mealLogManager)
                    .environmentObject(healthManager)
                    .tabItem {
                        Label("Glucose", systemImage: "waveform.path.ecg")
                    }
            }
        }
    }
}

