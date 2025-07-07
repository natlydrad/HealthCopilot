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
            
            Button("Load Glucose (March)") {
                let start = Calendar.current.date(from: DateComponents(year: 2025, month: 3, day: 1))!
                let end = Calendar.current.date(from: DateComponents(year: 2025, month: 3, day: 31))!

                healthManager.fetchGlucoseData(startDate: start, endDate: end) { samples in
                    self.glucoseData = samples
                    print("📊 Loaded \(samples.count) glucose points from March.")
                }
            }
            
            Button("Generate Insight") {
                guard let testMeal = mealLogManager.meals.first else {
                    print("⚠️ No meals found.")
                    return
                }

                let spike = healthManager.analyzeGlucoseImpact(for: testMeal, glucoseData: glucoseData)

                // Fake a recovery time for now (you can build real recovery detection next)
                let recoveryMinutes = 75  // Example: 1h15m recovery

                // Fake a personal comparison percentile (later we calculate this too)
                let percentile = 70.0

                if let spike = spike {
                    let insight = InsightGenerator.generateTags(for: spike, recoveryMinutes: recoveryMinutes, percentile: percentile)

                    print("📈 Spike Tag: \(insight.spikeTag)")
                    print("⏱ Recovery Tag: \(insight.recoveryTag)")
                    print("📊 Comparison: \(insight.personalComparisonTag)")
                    print("🏥 Healthy: \(insight.healthyRangeTag)")
                    print("🎯 Optimal: \(insight.optimalRangeTag)")
                    print("📝 Prompt:\n\(insight.prompt)")
                } else {
                    print("⚠️ Not enough glucose data to generate insight.")
                }
            }

            .padding()
        }
    }
}
