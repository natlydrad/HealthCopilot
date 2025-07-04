//
//  DashboardView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/4/25.
//

import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var healthManager: HealthManager

    var body: some View {
        VStack(spacing: 20) {
            Text("❤️ Heart Rate: \(Int(healthManager.latestHeartRate)) BPM")
            Text("💤 Sleep: \(String(format: "%.1f", healthManager.totalSleepHours)) hours")
            Text("💪 Exercise: \(Int(healthManager.exerciseMinutes)) minutes")
        }
        .padding()
        .onAppear {
            healthManager.fetchAllHealthData()
        }
    }
}
