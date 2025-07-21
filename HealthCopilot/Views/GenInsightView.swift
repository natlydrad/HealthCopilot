//
//  GenInsightView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/20/25.
//

import SwiftUI

struct GenInsightView: View {
    @EnvironmentObject var healthManager: HealthManager

    var body: some View {
        NavigationView {
            List {
                if healthManager.insights.isEmpty {
                    Text("No insights to show.")
                        .foregroundColor(.gray)
                } else {
                    ForEach(healthManager.insights) { insight in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(insight.summary)
                                .font(.headline)

                            if let detail = insight.detail {
                                Text(detail)
                                    .font(.subheadline)
                                    .foregroundColor(.gray)
                            }

                            Text(insight.date.formatted(date: .abbreviated, time: .omitted))
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 8)
                    }
                }
            }
            .navigationTitle("Insights")
            
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

