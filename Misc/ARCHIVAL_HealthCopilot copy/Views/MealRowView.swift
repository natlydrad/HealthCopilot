//
//  MealRowView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/6/25.
//

import SwiftUI

struct MealRowView: View {
    let meal: MealLog
    let insight: MealInsight

    var body: some View {
        let timeSinceMeal = Date().timeIntervalSince(meal.date) / 60
        let isReady = timeSinceMeal >= 120

        VStack(alignment: .leading) {
            Text(meal.name)
                .font(.headline)
            Text(meal.date, style: .date)
                .font(.subheadline)
            Text(meal.date, style: .time)
                .font(.subheadline)
            Text("Calories: \(Int(meal.calories)) kcal")
                .font(.subheadline)
            Text("Spike: \(String(format: "%.1f", insight.spikeValue)) mg/dL")
                .font(.subheadline)

            if isReady {
                Text("✅ Glucose analyzed")
                    .font(.caption)
                    .foregroundColor(.green)
            } else {
                Text("⏳ Awaiting glucose data...")
                    .font(.caption)
                    .foregroundColor(.orange)
            }
        }
    }
}
