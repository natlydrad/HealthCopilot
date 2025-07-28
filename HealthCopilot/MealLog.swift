//
//  MealLog.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import Foundation

struct MealLog: Identifiable, Codable {
    var id: UUID = UUID()
    var date: Date
    var name: String
    var notes: String?

    var ingredients: [Ingredient]

    // Auto-calculated from ingredients (or populated directly)
    var calories: Double
    var protein: Double
    var carbs: Double
    var fat: Double

    var spikeValue: Double?
    var auc: Double?
    var avgDelta: Double?
    var recoveryTime: Double?
    var responseScore: Double?

    var tags: [String]
}

struct Ingredient: Identifiable, Codable {
    var id: UUID = UUID()
    var name: String
    var unit: String
    var quantity: Double
    var mass: Double

    var calories: Double
    var carbs: Double
    var fat: Double
    var protein: Double

    var saturatedFat: Double?
    var transFat: Double?
    var monoFat: Double?
    var polyFat: Double?

    var cholesterol: Double?
    var sodium: Double?
    var fiber: Double?
    var sugar: Double?
    var sugarAdded: Double?

    var vitaminD: Double?
    var calcium: Double?
    var iron: Double?
    var potassium: Double?
    var vitaminA: Double?
    var vitaminC: Double?

    var alcohol: Double?
    var sugarAlcohol: Double?
    var vitaminB12: Double?
    var vitaminB12Added: Double?
    var vitaminB6: Double?
    var vitaminE: Double?
    var vitaminEAdded: Double?

    var magnesium: Double?
    var phosphorus: Double?
    var iodine: Double?
}


