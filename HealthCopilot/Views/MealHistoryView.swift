//
//  MealHistoryView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import SwiftUI
import UIKit

struct MealHistoryView: View {
    @EnvironmentObject var mealLogManager: MealLogManager
    @EnvironmentObject var healthManager: HealthManager
    @State private var didAutoExport = false
    
    var body: some View {
        NavigationStack {
            VStack {
                Text("Exporting Meal Events...")
                
                Button("Export CSV Again") {
                    exportAndShare()
                }
            }
            .navigationTitle("Meal Export")
            .onChange(of: mealLogManager.meals.count) { mealCount in
                if !didAutoExport && mealCount > 0 {
                    didAutoExport = true
                    exportAndShare()
                }
            }
        }
    }
    
    private func exportAndShare() {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        
        guard let start = formatter.date(from: "2025-07-07"),
              let end = formatter.date(from: "2025-07-27") else {
            print("❌ Invalid date range")
            return
        }
        
        // 1. Export glucose
        healthManager.exportGlucoseCSV(start: start, end: end)
        
        // 2. Build a file URL for sharing
        if let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first {
            let fileURL = dir.appendingPathComponent("GlucoseReadings.csv")
            
            // 3. Show iOS share sheet
            let av = UIActivityViewController(activityItems: [fileURL], applicationActivities: nil)
            
            // Present from root view controller
            if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
               let rootVC = windowScene.windows.first?.rootViewController {
                rootVC.present(av, animated: true, completion: nil)
            }
        }
    }
    
    
    /*
     private func exportAndShare() {
     print("🍔 meals.count =", mealLogManager.meals.count)
     print("📈 glucoseSamples.count =", healthManager.glucoseSamples.count)
     
     let mealEvents = fuseMealLogsWithGlucose(
     meals: mealLogManager.meals,
     glucoseData: healthManager.glucoseSamples
     )
     print("🧪 mealEvents.count =", mealEvents.count)
     
     let csv = exportMealEventsToCSV(events: mealEvents)
     shareCSV(csv)
     }
     }
     
     
     func exportMealEventsToCSV(events: [MealEvent]) -> String {
     var csv = "date,carbs,fiber,fat,protein,mealName,preMealGlucose,aucGlucose,spike,mealID\n"
     let formatter = ISO8601DateFormatter()
     
     for event in events {
     let safeMealName = event.mealName?.replacingOccurrences(of: "\"", with: "\"\"") ?? ""
     let quotedMealName = "\"\(safeMealName)\""
     
     let row = [
     formatter.string(from: event.timestamp),
     "\(event.carbs)",
     "\(event.fiber)",
     "\(event.fat)",
     "\(event.protein)",
     quotedMealName,
     "\(event.preMealGlucose ?? -1)",
     "\(event.aucGlucose ?? -1)",
     "\(event.spike == true ? 1 : 0)",
     event.mealID ?? ""
     ].joined(separator: ",")
     
     csv.append("\(row)\n")
     }
     
     return csv
     }
     
     func shareCSV(_ csv: String) {
     let fileName = "MealEvents.csv"
     let path = FileManager.default.temporaryDirectory.appendingPathComponent(fileName)
     
     do {
     try csv.write(to: path, atomically: true, encoding: .utf8)
     
     let activityVC = UIActivityViewController(activityItems: [path], applicationActivities: nil)
     if let window = UIApplication.shared.connectedScenes.first as? UIWindowScene,
     let rootVC = window.windows.first?.rootViewController {
     rootVC.present(activityVC, animated: true)
     }
     } catch {
     print("❌ CSV save error: \(error)")
     }
     }
     
     func fuseMealLogsWithGlucose(
     meals: [MealLog],
     glucoseData: [GlucoseSample],
     preMealWindowMinutes: Int = 30,
     postMealWindowMinutes: Int = 120
     ) -> [MealEvent] {
     var mealEvents: [MealEvent] = []
     
     print("🍔 Fusing \(meals.count) meals with \(glucoseData.count) CGM points")
     
     for meal in meals.prefix(3) {
     print("🍽️ Meal at:", meal.date)
     }
     for glucose in glucoseData.prefix(3) {
     print("🩸 CGM at:", glucose.date, "value:", glucose.value)
     }
     
     
     for meal in meals {
     let mealTime = meal.date
     
     // 1. Get CGM values 30 min before
     let preMealGlucose = glucoseData
     .filter { $0.date >= mealTime.addingTimeInterval(TimeInterval(-preMealWindowMinutes * 60)) &&
     $0.date < mealTime }
     .map { $0.value }
     
     let avgPreMealGlucose = preMealGlucose.isEmpty ? nil : preMealGlucose.reduce(0, +) / Double(preMealGlucose.count)
     
     // 2. Get CGM values 2h after
     let postMealGlucose = glucoseData
     .filter { $0.date >= mealTime &&
     $0.date <= mealTime.addingTimeInterval(TimeInterval(postMealWindowMinutes * 60)) }
     
     let auc = calculateAUC(postMealGlucose: postMealGlucose, baseline: avgPreMealGlucose)
     
     print("🔍 Meal at \(mealTime)")
     print("  Pre-meal CGM count:", preMealGlucose.count)
     print("  Post-meal CGM count:", postMealGlucose.count)
     
     
     // 3. Determine spike (e.g., if value ever > 140)
     let spike = postMealGlucose.contains { $0.value > 140 }
     
     // 4. Build MealEvent
     let event = MealEvent(
     timestamp: mealTime,
     carbs: meal.carbs,
     fiber: meal.ingredients.reduce(0) { $0 + ($1.fiber ?? 0) },
     fat: meal.fat,
     protein: meal.protein,
     mealName: meal.name,
     preMealGlucose: avgPreMealGlucose,
     aucGlucose: auc,
     spike: spike,
     sleepPreviousNight: nil,
     stepsBeforeMeal: nil,
     heartRateBeforeMeal: nil,
     //moodBeforeMeal: nil,
     mealID: meal.id.uuidString
     )
     
     mealEvents.append(event)
     }
     
     return mealEvents
     }
     
     func calculateAUC(postMealGlucose: [GlucoseSample], baseline: Double?) -> Double? {
     guard let baseline = baseline, postMealGlucose.count >= 2 else { return nil }
     
     let sorted = postMealGlucose.sorted { $0.date < $1.date }
     
     var auc = 0.0
     for i in 1..<sorted.count {
     let dt = sorted[i].date.timeIntervalSince(sorted[i-1].date) / 60.0 // minutes
     let val1 = sorted[i-1].value - baseline
     let val2 = sorted[i].value - baseline
     let trapezoid = max((val1 + val2) / 2, 0) * dt
     auc += trapezoid
     }
     
     return auc
     }
     
     
     
     List {
     ForEach(mealLogManager.meals, id: \.id) { meal in
     VStack(alignment: .leading, spacing: 4) {
     Text(meal.name).font(.headline)
     Text(meal.date.formatted(date: .abbreviated, time: .shortened))
     .font(.subheadline).foregroundColor(.secondary)
     Text("Calories: \(Int(meal.calories)) • Protein: \(Int(meal.protein))g • Carbs: \(Int(meal.carbs))g • Fat: \(Int(meal.fat))g")
     .font(.caption)
     }
     .padding(.vertical, 4)
     }
     }*/
}
