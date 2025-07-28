//
//  MealInsightView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/6/25.
//

import SwiftUI

struct MealInsightView: View {
    let meal: MealLog
    let insight: MealInsight
    let averageSpike: Double

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text("🍽 Meal: \(meal.name) at \(formattedDate(meal.date))")

                Text("📈 Spike: +\(Int(insight.spikeValue)) mg/dL → \(insight.spikeTag)")
                    .font(.subheadline)
                    .foregroundColor(.primary)
                Text("(≤20: Minimal, 20–40: Moderate, 40–60: High, >60: Very High)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Text("⏱ Recovery: \(insight.recoveryMinutes) min → \(insight.recoveryTag)")
                    .font(.subheadline)
                    .foregroundColor(.primary)
                Text("(≤60: Fast, 60–120: Normal, 120–180: Slow, >180: Very Slow)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                /*Text("📊 Spike \(insight.personalComparisonTag) (Your 7-day average: +\(Int(averageSpike)) mg/dL)")
                    .font(.subheadline)*/

                Text("🏥 \(insight.healthyRangeTag) (≤30 mg/dL)")
                    .font(.subheadline)

                Text("🎯 \(insight.optimalRangeTag) (≤20 mg/dL)")
                    .font(.subheadline)
            }
            .padding()
        }
        .navigationTitle("Meal Insight")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func formattedDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}
