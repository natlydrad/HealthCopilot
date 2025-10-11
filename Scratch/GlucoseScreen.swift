//
//  GlucoseScreen.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI

struct GlucoseScreen: View {
    @EnvironmentObject var mealLogManager: MealLogManager
    @EnvironmentObject var healthManager: HealthManager
    @State private var glucoseData: [GlucoseSample] = []
    @State private var glucoseEvents: [GlucoseEvent] = []
    
    // Use one selected day
    @State private var selectedDay: Date = Calendar.current.date(byAdding: .day, value: -1, to: Date())!
    
    // Computed start/end dates aligned to 6 AM
    var adjustedStartDate: Date {
        Calendar.current.date(bySettingHour: 6, minute: 0, second: 0, of: selectedDay)!
    }

    var adjustedEndDate: Date {
        Calendar.current.date(byAdding: .hour, value: 24, to: adjustedStartDate)!
    }
    
    var body: some View {
        VStack {
            DatePicker("Day", selection: $selectedDay, displayedComponents: .date)
            
            Button("Load Glucose") {
                healthManager.fetchGlucoseData(startDate: adjustedStartDate, endDate: adjustedEndDate) { samples in
                    self.glucoseData = samples
                    self.glucoseEvents = healthManager.detectGlucoseEvents(from: samples)
                    print("📊 Detected \(glucoseEvents.count) events.")
                    for event in glucoseEvents {
                        print("Event: \(event.startTime) → \(event.endTime) | AUC: \(event.auc), Peak: \(event.peakDelta), Color: \(event.color)")
                    }
                }
            }
            
            GlucoseGraphView(
                glucoseData: glucoseData,
                mealData: mealLogManager.meals,
                startDate: adjustedStartDate,
                endDate: adjustedEndDate
            )
            .frame(height: 300)
            .padding()
        }
    }
}
