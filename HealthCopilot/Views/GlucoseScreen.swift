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
    
    @State private var startDate: Date = Calendar.current.date(byAdding: .day, value: -1, to: Date())!
    @State private var endDate: Date = Date()
    
    var body: some View {
        VStack {
            DatePicker("Start", selection: $startDate, displayedComponents: .date)
            DatePicker("End", selection: $endDate, displayedComponents: .date)
            
            Button("Load Glucose") {
                healthManager.fetchGlucoseData(startDate: startDate, endDate: endDate) { samples in
                    self.glucoseData = samples
                    self.glucoseEvents = healthManager.detectGlucoseEvents(from: samples)
                    print("📊 Detected \(glucoseEvents.count) events.")
                    for event in glucoseEvents {
                        print("Event: \(event.startTime) → \(event.endTime) | AUC: \(event.auc), Peak: \(event.peakDelta), Color: \(event.color)")
                    }
                }
                    
            }
            GlucoseGraphView(glucoseData: glucoseData, mealData: mealLogManager.meals, startDate: startDate, endDate: endDate)
            
            .frame(height: 300)
            .padding()
        }
    }
}
