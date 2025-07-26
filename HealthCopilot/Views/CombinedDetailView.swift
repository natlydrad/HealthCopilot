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
                    Text(fasting.detail ?? "No details available")
                        .font(.body)
                }
            }

            if let auc = aucInsight {
                Section(header: Text("AUC")) {
                    Text(auc.detail ?? "No details available")
                        .font(.body)
                }
            }
        }
        .navigationTitle("Details")
    }
}
