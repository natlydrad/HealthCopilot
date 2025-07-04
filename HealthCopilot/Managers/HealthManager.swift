//
//  HealthManager.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/4/25.
//

import Foundation
import HealthKit

class HealthManager: ObservableObject {
    let healthStore = HKHealthStore()
    
    @Published var totalSleepHours: Double = 0.0
    @Published var exerciseMinutes: Double = 0.0
    @Published var latestHeartRate: Double = 0.0
    
    init() {
        requestAuthorization()
    }
    
    func requestAuthorization() {
        let readTypes: Set = [
            HKObjectType.quantityType(forIdentifier: .heartRate)!,
            HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!,
            HKObjectType.quantityType(forIdentifier: .appleExerciseTime)!
        ]
        
        healthStore.requestAuthorization(toShare: [], read: readTypes) { success, error in
            if success {
                DispatchQueue.main.async {
                    self.fetchAllHealthData()
                }
            } else {
                print("Authorization failed: \(String(describing: error))")
            }
        }
    }
    
    func fetchAllHealthData() {
        fetchHeartRate()
        fetchSleepData()
        fetchExerciseData()
    }
    
    func fetchHeartRate() {
        guard let heartRateType = HKQuantityType.quantityType(forIdentifier: .heartRate) else { return }
        
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
        let query = HKSampleQuery(sampleType: heartRateType, predicate: nil, limit: 1, sortDescriptors: [sortDescriptor]) { query, samples, error in
            guard let sample = samples?.first as? HKQuantitySample else { return }
            
            let bpm = sample.quantity.doubleValue(for: HKUnit(from: "count/min"))
            
            DispatchQueue.main.async {
                self.latestHeartRate = bpm
            }
        }
        
        healthStore.execute(query)
    }

    
    func fetchSleepData() {
        guard let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) else { return }
        
        let startDate = Calendar.current.date(byAdding: .day, value: -1, to: Date())
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: Date(), options: .strictStartDate)
        
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
        let query = HKSampleQuery(sampleType: sleepType, predicate: predicate, limit: 0, sortDescriptors: [sortDescriptor]) { query, samples, error in
            
            var totalSleep = 0.0
            
            for sample in samples as? [HKCategorySample] ?? [] {
                if sample.value != HKCategoryValueSleepAnalysis.inBed.rawValue {
                    let sleepTime = sample.endDate.timeIntervalSince(sample.startDate)
                    totalSleep += sleepTime
                }
            }
            
            let hours = totalSleep / 3600.0
            
            DispatchQueue.main.async {
                self.totalSleepHours = hours
            }
        }
        
        healthStore.execute(query)
    }
    
    func fetchWeeklySleepData(completion: @escaping (String) -> Void) {
        guard let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) else { return }

        let startDate = Calendar.current.date(byAdding: .day, value: -7, to: Date())
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: Date(), options: .strictStartDate)

        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
        let query = HKSampleQuery(sampleType: sleepType, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: [sortDescriptor]) { query, samples, error in

            var sleepByDay: [String: Double] = [:]

            for sample in samples as? [HKCategorySample] ?? [] {
                if sample.value != HKCategoryValueSleepAnalysis.inBed.rawValue {
                    let sleepTime = sample.endDate.timeIntervalSince(sample.startDate)
                    let dateKey = DateFormatter.localizedString(from: sample.startDate, dateStyle: .short, timeStyle: .none)
                    sleepByDay[dateKey, default: 0.0] += sleepTime
                }
            }

            var summary = "Your sleep over the past 7 days:\n"
            for (date, seconds) in sleepByDay.sorted(by: { $0.key < $1.key }) {
                let hours = seconds / 3600.0
                summary += "\(date): \(String(format: "%.1f", hours)) hours\n"
            }

            completion(summary)
        }

        healthStore.execute(query)
    }

    
    func fetchExerciseData() {
        guard let exerciseType = HKQuantityType.quantityType(forIdentifier: .appleExerciseTime) else { return }
        
        let startDate = Calendar.current.startOfDay(for: Date())
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: Date(), options: .strictStartDate)
        
        let query = HKStatisticsQuery(quantityType: exerciseType, quantitySamplePredicate: predicate, options: .cumulativeSum) { query, result, error in
            
            guard let sum = result?.sumQuantity() else { return }
            let minutes = sum.doubleValue(for: HKUnit.minute())
            
            DispatchQueue.main.async {
                self.exerciseMinutes = minutes
            }
        }
        
        healthStore.execute(query)
    }

    
    func fetchGPTSummary(prompt: String, completion: @escaping (String?) -> Void) {
        let apiKey = ProcessInfo.processInfo.environment["OPENAI_API_KEY"] ?? ""
        let url = URL(string: "https://api.openai.com/v1/chat/completions")!

        let headers = [
            "Authorization": "Bearer \(apiKey)",
            "Content-Type": "application/json"
        ]

        let body: [String: Any] = [
            "model": "gpt-3.5-turbo",  // Or use "gpt-4o" if you prefer
            "messages": [
                ["role": "system", "content": "You are a friendly health coach who gives short, helpful advice based on sleep data."],
                ["role": "user", "content": prompt]
            ],
            "temperature": 0.7
        ]

        let jsonData = try! JSONSerialization.data(withJSONObject: body)

        var request = URLRequest(url: url)
        request.allHTTPHeaderFields = headers
        request.httpMethod = "POST"
        request.httpBody = jsonData

        URLSession.shared.dataTask(with: request) { data, response, error in
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let choices = json["choices"] as? [[String: Any]],
                  let message = choices.first?["message"] as? [String: Any],
                  let content = message["content"] as? String else {
                completion(nil)
                return
            }
            completion(content)
        }.resume()
    }


}
