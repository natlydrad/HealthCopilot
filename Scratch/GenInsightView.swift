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
    @State private var fastingInsights: [GlucoseInsight] = []
    @State private var aucInsights: [GlucoseInsight] = []

    struct TimeRangeInsights: Identifiable {
        let id: UUID
        let dayCount: Int         // <-- You were trying to use this in your return!
        let range: String         // e.g. "Last 14 days"
        let fastingInsight: GlucoseInsight?
        let aucInsight: GlucoseInsight?

        init(dayCount: Int, range: String, fastingInsight: GlucoseInsight?, aucInsight: GlucoseInsight?) {
            self.id = UUID()
            self.dayCount = dayCount
            self.range = range
            self.fastingInsight = fastingInsight
            self.aucInsight = aucInsight
        }
    }


    var body: some View {
        NavigationView {
            List {
                Section(header: Text("Insights").font(.largeTitle.bold())) {
                    ForEach(combinedInsights(fastingInsights: fastingInsights, aucInsights: aucInsights), id: \.range) { entry in
                        NavigationLink(destination: CombinedDetailView(
                            fastingInsight: entry.fastingInsight,
                            aucInsight: entry.aucInsight
                        )) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(entry.range)
                                    .font(.headline)

                                if let fasting = entry.fastingInsight {
                                    Text(fasting.summary)
                                }

                                if let auc = entry.aucInsight {
                                    Text(auc.summary)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }
            }
        }

            .onAppear {
                let end = Date()
                let start = Calendar.current.date(byAdding: .day, value: -100, to: end)!

                healthManager.fetchGlucoseData(startDate: start, endDate: end) { samples in
                    let fastingResults = healthManager.getFastingGlucose(from: samples)
                    let aucResults = healthManager.generateAUCResults(from: samples)

                    let newFastingInsights = [
                        healthManager.generateFastingGlucoseInsight(from: fastingResults, days: 3),
                        healthManager.generateFastingGlucoseInsight(from: fastingResults, days: 7),
                        healthManager.generateFastingGlucoseInsight(from: fastingResults, days: 14),
                        healthManager.generateFastingGlucoseInsight(from: fastingResults, days: 90)
                    ].flatMap { $0 }

                    let newAUCInsights = [
                        healthManager.generateAUCInsight(from: aucResults, days: 3),
                        healthManager.generateAUCInsight(from: aucResults, days: 7),
                        healthManager.generateAUCInsight(from: aucResults, days: 14),
                        healthManager.generateAUCInsight(from: aucResults, days: 90)
                    ].flatMap { $0 }

                    DispatchQueue.main.async {
                        self.fastingInsights = newFastingInsights
                        self.aucInsights = newAUCInsights
                        healthManager.insights = newFastingInsights + newAUCInsights
                    }
                }
            }

        }
    }

    func combinedInsights(
        fastingInsights: [GlucoseInsight],
        aucInsights: [GlucoseInsight]
    ) -> [TimeRangeInsights] {

        print("⏳ Starting combinedInsights()...")
        print("fasting time spans: \(fastingInsights.map { $0.timeSpanLabel })")
        print("auc time spans: \(aucInsights.map { $0.timeSpanLabel })")

        let allRanges = Set(fastingInsights.map { $0.timeSpanLabel })
            .union(aucInsights.map { $0.timeSpanLabel })

        let combined = allRanges.compactMap { range -> TimeRangeInsights? in
            let fasting = fastingInsights.first(where: { $0.timeSpanLabel == range })
            let auc = aucInsights.first(where: { $0.timeSpanLabel == range })
            let dayCount = extractDayCount(from: range)

            return TimeRangeInsights(
                dayCount: dayCount,
                range: range,
                fastingInsight: fasting,
                aucInsight: auc
            )
        }

        print("✅ Combined insight count: \(combined.count)")
        return combined.sorted(by: { $0.dayCount < $1.dayCount })
    }


    func extractDayCount(from range: String) -> Int {
        let digits = range.components(separatedBy: CharacterSet.decimalDigits.inverted).joined()
        return Int(digits) ?? 0
    }


