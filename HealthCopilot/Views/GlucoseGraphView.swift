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

    var body: some View {
        Chart {
            ForEach(glucoseData) { sample in
                LineMark(
                    x: .value("Time", sample.date),
                    y: .value("Glucose", sample.value)
                )
            }

            ForEach(mealData) { meal in
                PointMark(
                    x: .value("Time", meal.date),
                    y: .value("Meal", 0)  // anchored low or baseline
                )
                .foregroundStyle(.red)
                
            }
        }
        
        .chartXScale(domain: Calendar.current.date(from: DateComponents(year: 2025, month: 3, day: 25))!
                    ...
                    Calendar.current.date(from: DateComponents(year: 2025, month: 3, day: 26))!)
        .frame(height: 300)
        .padding()
    }
}
