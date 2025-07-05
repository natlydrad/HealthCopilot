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
            HKObjectType.quantityType(forIdentifier: .appleExerciseTime)!,
        ]
        
        let writeTypes: Set = [
            HKObjectType.quantityType(forIdentifier: .dietaryEnergyConsumed)!,
            HKObjectType.quantityType(forIdentifier: .dietaryProtein)!,
            HKObjectType.quantityType(forIdentifier: .dietaryCarbohydrates)!,
            HKObjectType.quantityType(forIdentifier: .dietaryFatTotal)!,
        ]
        
        
        healthStore.requestAuthorization(toShare: writeTypes, read: readTypes) { success, error in
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
    
    func fetchSleepDataForToday(completion: @escaping (Double) -> Void) {
        guard let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) else { return }
        
        let startDate = Calendar.current.date(byAdding: .hour, value: -24, to: Date()) ?? Date()
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: Date(), options: .strictStartDate)
        
        let query = HKSampleQuery(sampleType: sleepType, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { query, samples, error in
            
            var totalSleep = 0.0
            
            for sample in samples as? [HKCategorySample] ?? [] {
                if sample.value != HKCategoryValueSleepAnalysis.inBed.rawValue {
                    let sleepTime = sample.endDate.timeIntervalSince(sample.startDate)
                    totalSleep += sleepTime
                }
            }
            
            let hours = totalSleep / 3600.0
            completion(hours)
        }
        
        healthStore.execute(query)
    }
    
    func fetchExerciseDataForToday(completion: @escaping (Double) -> Void) {
        guard let exerciseType = HKQuantityType.quantityType(forIdentifier: .appleExerciseTime) else { return }
        
        let startDate = Calendar.current.startOfDay(for: Date())
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: Date(), options: .strictStartDate)
        
        let query = HKStatisticsQuery(quantityType: exerciseType, quantitySamplePredicate: predicate, options: .cumulativeSum) { query, result, error in
            
            guard let sum = result?.sumQuantity() else {
                completion(0.0)
                return
            }
            
            let minutes = sum.doubleValue(for: HKUnit.minute())
            completion(minutes)
        }
        
        healthStore.execute(query)
    }
    
    func fetchHeartRateData(completion: @escaping (Double) -> Void) {
        guard let heartRateType = HKQuantityType.quantityType(forIdentifier: .heartRate) else { return }
        
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
        let query = HKSampleQuery(sampleType: heartRateType, predicate: nil, limit: 1, sortDescriptors: [sortDescriptor]) { query, samples, error in
            
            guard let sample = samples?.first as? HKQuantitySample else {
                completion(0.0)
                return
            }
            
            let bpm = sample.quantity.doubleValue(for: HKUnit(from: "count/min"))
            completion(bpm)
        }
        
        healthStore.execute(query)
    }
    
    
    func fetchDailyHealthSummary(completion: @escaping (String) -> Void) {
        var sleepHours: Double?
        var exerciseMinutes: Double?
        var heartRate: Double?
        
        let group = DispatchGroup()
        
        // Fetch Sleep
        group.enter()
        fetchSleepDataForToday { hours in
            sleepHours = hours
            group.leave()
        }
        
        // Fetch Exercise
        group.enter()
        fetchExerciseDataForToday { minutes in
            exerciseMinutes = minutes
            group.leave()
        }
        
        // Fetch Heart Rate
        group.enter()
        fetchHeartRateData { bpm in
            heartRate = bpm
            group.leave()
        }
        
        group.notify(queue: .main) {
            let sleepStr = sleepHours != nil ? String(format: "%.1f hours", sleepHours!) : "no sleep data"
            let exerciseStr = exerciseMinutes != nil ? String(format: "%.0f minutes", exerciseMinutes!) : "no exercise data"
            let heartRateStr = heartRate != nil ? String(format: "%.0f bpm", heartRate!) : "no heart rate data"
            
            let summary = """
            Today:
            Sleep: \(sleepStr)
            Exercise: \(exerciseStr)
            Heart Rate: \(heartRateStr)
            """
            
            completion(summary)
        }
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
                //["role": "system", "content": "You are a friendly health coach who gives short, helpful advice based on sleep data."],
                ["role": "system", "content": "You are a helpful nutrition assistant. Based on the user's food description, estimate total Calories (kcal), Protein (g), Carbs (g), and Fat (g). Respond ONLY with these values in the following format: \nCalories: X kcal\nProtein: Y g\nCarbs: Z g\nFat: W g"],
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
    
    func parseNutrition(from response: String) -> (calories: Double, protein: Double, carbs: Double, fat: Double)? {
        var calories: Double = 0
        var protein: Double = 0
        var carbs: Double = 0
        var fat: Double = 0
        
        let lines = response.components(separatedBy: .newlines)
        
        for line in lines {
            if line.lowercased().contains("calories") {
                calories = Double(line.components(separatedBy: CharacterSet.decimalDigits.inverted).joined()) ?? 0
            } else if line.lowercased().contains("protein") {
                protein = Double(line.components(separatedBy: CharacterSet.decimalDigits.inverted).joined()) ?? 0
            } else if line.lowercased().contains("carb") {
                carbs = Double(line.components(separatedBy: CharacterSet.decimalDigits.inverted).joined()) ?? 0
            } else if line.lowercased().contains("fat") {
                fat = Double(line.components(separatedBy: CharacterSet.decimalDigits.inverted).joined()) ?? 0
            }
        }
        
        return (calories, protein, carbs, fat)
    }
    
    func saveNutritionToHealthKit(calories: Double, protein: Double, carbs: Double, fat: Double) {
        let now = Date()
        
        guard
            let energyType = HKObjectType.quantityType(forIdentifier: .dietaryEnergyConsumed),
            let proteinType = HKObjectType.quantityType(forIdentifier: .dietaryProtein),
            let carbType = HKObjectType.quantityType(forIdentifier: .dietaryCarbohydrates),
            let fatType = HKObjectType.quantityType(forIdentifier: .dietaryFatTotal)
        else { return }
        
        let energyQuantity = HKQuantity(unit: .kilocalorie(), doubleValue: calories)
        let proteinQuantity = HKQuantity(unit: .gram(), doubleValue: protein)
        let carbQuantity = HKQuantity(unit: .gram(), doubleValue: carbs)
        let fatQuantity = HKQuantity(unit: .gram(), doubleValue: fat)
        
        let samples: [HKQuantitySample] = [
            HKQuantitySample(type: energyType, quantity: energyQuantity, start: now, end: now),
            HKQuantitySample(type: proteinType, quantity: proteinQuantity, start: now, end: now),
            HKQuantitySample(type: carbType, quantity: carbQuantity, start: now, end: now),
            HKQuantitySample(type: fatType, quantity: fatQuantity, start: now, end: now)
        ]
        
        healthStore.save(samples) { success, error in
            if success {
                print("✅ Nutrition data saved to HealthKit")
            } else if let error = error {
                print("❌ Error saving to HealthKit: \(error.localizedDescription)")
            }
        }
    }
    
    func deleteNutritionData(for date: Date) {
        let types: [HKQuantityTypeIdentifier] = [
            .dietaryEnergyConsumed,
            .dietaryProtein,
            .dietaryCarbohydrates,
            .dietaryFatTotal
        ]

        // Tight window: meal timestamp ± 1 second
        let start = date.addingTimeInterval(-1)
        let end = date.addingTimeInterval(1)

        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        for typeIdentifier in types {
            guard let type = HKObjectType.quantityType(forIdentifier: typeIdentifier) else { continue }

            let query = HKSampleQuery(sampleType: type, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { query, samples, error in
                guard let samples = samples, !samples.isEmpty else {
                    print("❌ No samples found for deletion for type: \(typeIdentifier.rawValue)")
                    return
                }

                self.healthStore.delete(samples) { success, error in
                    if success {
                        print("✅ Deleted \(samples.count) samples for \(typeIdentifier.rawValue)")
                    } else {
                        print("❌ Deletion failed for \(typeIdentifier.rawValue): \(error?.localizedDescription ?? "Unknown error")")
                    }
                }
            }

            healthStore.execute(query)
        }
    }

}

