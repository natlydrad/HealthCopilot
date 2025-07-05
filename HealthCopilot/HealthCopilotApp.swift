//
//  HealthCopilotApp.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI

@main
struct HealthCopilotApp: App {
    var body: some Scene {
        WindowGroup {
            TabView {
                NutritionView()
                    .tabItem {
                        Label("Log Meal", systemImage: "plus.circle")
                    }

                MealHistoryView()
                    .tabItem {
                        Label("History", systemImage: "list.bullet")
                    }
                
                GlucoseScreen()
                    .tabItem {
                        Label("Glucose", systemImage: "waveform.path.ecg")
                    }
            }
        }
    }
}

