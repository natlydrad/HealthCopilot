//
//  HealthCopilotApp.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/3/25.
//

/*
import SwiftUI

@main
struct HealthCopilotApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
*/

// Spezi + HealthKit Minimal Starter App

import SwiftUI
import HealthKit

@main
struct HealthCopilotApp: App {
    @StateObject private var healthManager = HealthManager()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(healthManager)
                .onAppear {
                    healthManager.requestAuthorization()
                }
        }
    }
}

class HealthManager: ObservableObject {
    private var healthStore = HKHealthStore()

    @Published var stepCount: Double = 0
    @Published var heartRate: Double = 0

    func requestAuthorization() {
        let readTypes: Set = [
            HKObjectType.quantityType(forIdentifier: .stepCount)!,
            HKObjectType.quantityType(forIdentifier: .heartRate)!
        ]

        healthStore.requestAuthorization(toShare: [], read: readTypes) { success, error in
            if success {
                self.fetchStepCount()
                self.fetchHeartRate()
            } else if let error = error {
                print("HealthKit Authorization Failed: \(error.localizedDescription)")
            }
        }
    }

    func fetchStepCount() {
        let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount)!
        let startOfDay = Calendar.current.startOfDay(for: Date())
        let predicate = HKQuery.predicateForSamples(withStart: startOfDay, end: Date(), options: .strictStartDate)

        let query = HKStatisticsQuery(quantityType: stepType, quantitySamplePredicate: predicate, options: .cumulativeSum) { _, result, _ in
            DispatchQueue.main.async {
                self.stepCount = result?.sumQuantity()?.doubleValue(for: .count()) ?? 0
            }
        }

        healthStore.execute(query)
    }

    func fetchHeartRate() {
        let hrType = HKQuantityType.quantityType(forIdentifier: .heartRate)!
        let mostRecentPredicate = HKQuery.predicateForSamples(withStart: Calendar.current.date(byAdding: .day, value: -1, to: Date()), end: Date(), options: .strictStartDate)

        let query = HKSampleQuery(sampleType: hrType, predicate: mostRecentPredicate, limit: 1, sortDescriptors: [NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)]) { _, results, _ in
            DispatchQueue.main.async {
                if let sample = results?.first as? HKQuantitySample {
                    self.heartRate = sample.quantity.doubleValue(for: HKUnit(from: "count/min"))
                }
            }
        }

        healthStore.execute(query)
    }
}
