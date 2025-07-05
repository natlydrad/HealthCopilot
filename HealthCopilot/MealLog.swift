//
//  MealLog.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import Foundation

struct MealLog: Identifiable, Codable {
    var id: UUID = UUID()
    var description: String
    var date: Date
    var calories: Double
    var protein: Double
    var carbs: Double
    var fat: Double
}

