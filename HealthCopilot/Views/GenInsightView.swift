//
//  GenInsightView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/20/25.
//

import SwiftUI

struct GenInsightView: View {
    @EnvironmentObject var healthManager: HealthManager
    @State private var expandedInsightIDs: Set<UUID> = []

    var body: some View {
        NavigationView {
            VStack(alignment: .leading, spacing: 4) {
                // Header
                Text("Insights")
                    .font(.largeTitle.bold())
                    .padding(.horizontal)

                // Central Date
                Text(Date().formatted(date: .long, time: .omitted))
                    .font(.subheadline)
                    .foregroundColor(.gray)
                    .padding(.horizontal)

                List {
                    if healthManager.insights.isEmpty {
                        Text("No insights to show.")
                            .foregroundColor(.gray)
                    } else {
                        ForEach(healthManager.insights) { insight in
                            VStack(alignment: .leading, spacing: 6) {
                                Text(insight.timeSpanLabel)
                                    .font(.headline)

                                Text(insight.summary)
                                    .font(.subheadline)
                                    .foregroundColor(.gray)

                                if insight.detail != nil || insight.mathStats != nil {
                                    DisclosureGroup("See details") {
                                        VStack(alignment: .leading, spacing: 4) {
                                            if let detail = insight.detail {
                                                Text(detail)
                                            }

                                            if let stats = insight.mathStats {
                                                Text("• Slope: \(String(format: "%.2f", stats.slope)) mg/dL/day")
                                                Text("• R²: \(String(format: "%.2f", stats.rSquared))")
                                                Text("• Start: \(stats.start) mg/dL")
                                                Text("• End: \(stats.end) mg/dL")
                                            }
                                        }
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                        .padding(.top, 4)
                                    }
                                }
                            }
                            .padding(.vertical, 8)

                        }
                    }
                }
            }
            .onAppear {
                let end = Date()
                let start = Calendar.current.date(byAdding: .day, value: -100, to: end)!

                healthManager.fetchGlucoseData(startDate: start, endDate: end) { samples in
                    let fastingResults = healthManager.getFastingGlucose(from: samples)

                    let insights = [
                        healthManager.generateFastingGlucoseInsight(from: fastingResults, days: 3),
                        healthManager.generateFastingGlucoseInsight(from: fastingResults, days: 7),
                        healthManager.generateFastingGlucoseInsight(from: fastingResults, days: 14),
                        healthManager.generateFastingGlucoseInsight(from: fastingResults, days: 90)
                    ].flatMap { $0 }

                    DispatchQueue.main.async {
                        healthManager.insights = insights
                    }
                }
            }
        }
    }
}
