//
//  GlucoseGraphView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI
import Charts

struct GlucoseGraphView: View {
    var glucoseData: [GlucoseSample]
    var mealData: [MealLog]
    var startDate: Date
    var endDate: Date

    var body: some View {
        Chart {
            ForEach(glucoseData) { sample in
                LineMark(
                    x: .value("Time", sample.date),
                    y: .value("Glucose", sample.value)
                )
            }

            ForEach(mealData.filter { $0.date >= startDate && $0.date <= endDate }) { meal in
                PointMark(
                    x: .value("Time", meal.date),
                    y: .value("Meal", 0)
                )
                .foregroundStyle(.red)
            }
        }
        .chartXScale(domain: startDate ... endDate)
    }
}
