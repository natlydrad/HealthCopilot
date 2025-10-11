//
//  CombinedDetailView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/25/25.
//

import SwiftUI

struct CombinedDetailView: View {
    let fastingInsight: GlucoseInsight?
    let aucInsight: GlucoseInsight?

    var body: some View {
        List {
            if let fasting = fastingInsight {
                Section(header: Text("Fasting Glucose")) {
                    insightDetails(fasting)
                }
            }

            if let auc = aucInsight {
                Section(header: Text("AUC")) {
                    insightDetails(auc)
                }
            }
        }
        .navigationTitle("Details")
    }
}


@ViewBuilder
func insightDetails(_ insight: GlucoseInsight) -> some View {
    VStack(alignment: .leading, spacing: 4) {
        if let detail = insight.detail {
            Text(detail)
                .font(.body)
        }

        if let stats = insight.mathStats {
            VStack(alignment: .leading, spacing: 2) {
                Text("• Slope: \(String(format: "%.2f", stats.slope)) \(stats.unit)/day")
                Text("• R²: \(String(format: "%.2f", stats.rSquared))")
                Text("• Start: \(Int(stats.start)) \(stats.unit)")
                Text("• End: \(Int(stats.end)) \(stats.unit)")
                
            }
            .font(.subheadline)
            .foregroundColor(.gray)
            .padding(.top, 4)
        }
    }
    .padding(.vertical, 6)
}

