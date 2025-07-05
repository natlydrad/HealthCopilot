//
//  GlucoseScreen.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI

struct GlucoseScreen: View {
    @StateObject var healthManager = HealthManager()
    @StateObject var mealLogManager = MealLogManager()
    @State private var glucoseData: [GlucoseSample] = []

    var body: some View {
        VStack {
            GlucoseGraphView(glucoseData: glucoseData, mealData: mealLogManager.meals)
            
            /*
            Button("Load Glucose (Last 24h)") {
                let end = Date()
                let start = Calendar.current.date(byAdding: .hour, value: -24, to: end)!

                healthManager.fetchGlucoseData(startDate: start, endDate: end) { samples in
                    self.glucoseData = samples
                }
             */
            
            Button("Load Glucose (March)") {
                let start = Calendar.current.date(from: DateComponents(year: 2025, month: 3, day: 1))!
                let end = Calendar.current.date(from: DateComponents(year: 2025, month: 3, day: 31))!

                healthManager.fetchGlucoseData(startDate: start, endDate: end) { samples in
                    self.glucoseData = samples
                    print("📊 Loaded \(samples.count) glucose points from March.")
                }
            }
            .padding()
        }
    }
}

