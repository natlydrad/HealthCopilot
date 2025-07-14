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
    var glucoseEvents: [GlucoseEvent]

    var body: some View {
        // Filtered data to avoid weird spikes
        let filteredGlucose = glucoseData.filter {
            $0.date >= startDate && $0.date <= endDate && $0.value > 30 && $0.value < 400
        }

        ScrollView(.horizontal) {
            Chart {
                ForEach(glucoseEvents) { event in
                    RectangleMark(
                        xStart: .value("Start", event.startTime),
                        xEnd: .value("End", event.endTime),
                        yStart: .value("Low", 0),
                        yEnd: .value("High", 250)  // Adjust to your graph scale
                    )
                    .foregroundStyle(colorForEvent(event.color).opacity(0.2))
                }

                
                // Glucose line
                ForEach(filteredGlucose) { sample in
                    LineMark(
                        x: .value("Time", sample.date),
                        y: .value("Glucose", sample.value)
                    )
                }

                // Meal markers
                ForEach(mealData.filter { $0.date >= startDate && $0.date <= endDate }) { meal in
                    PointMark(
                        x: .value("Time", meal.date),
                        y: .value("Meal", 0)
                    )
                    .foregroundStyle(.red)
                }
            }
            .chartXScale(domain: startDate ... endDate)
            .chartYScale(domain: 0...200) // ✅ lock y-axis range
            .chartYAxis {
                AxisMarks(position: .leading)
            }
            .chartXAxis {
                AxisMarks(values: .stride(by: .hour, count: 2)) { value in
                    AxisGridLine()
                    AxisTick()
                    AxisValueLabel(anchor: .top) {
                        if let date = value.as(Date.self) {
                            Text(date.formatted(.dateTime.hour(.defaultDigits(amPM: .abbreviated))))
                        }
                    }
                }
            }
            .frame(minWidth: 1440, maxHeight: 300)
            .padding(.top, 16)     // ✅ fix label cutoff at top
            .padding(.leading, 8)  // ✅ ensure left labels are visible
        }
    }
}

func colorForEvent(_ color: GlucoseColor) -> Color {
    switch color {
    case .green:
        return .green
    case .white:
        return .gray
    case .yellow:
        return .yellow
    case .red:
        return .red
    }
}
