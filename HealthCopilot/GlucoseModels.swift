//
//  GlucoseSample.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import Foundation

struct GlucoseSample: Identifiable {
    let id = UUID()
    let date: Date
    let value: Double  // mg/dL
}

struct GlucoseEvent: Identifiable {
    let id = UUID()
    let startTime: Date
    let endTime: Date
    let peakDelta: Double
    let auc: Double
    let recovered: Bool
    let color: GlucoseColor
}

struct FastingGlucoseResult {
    let id = UUID()
    let date: Date
    let value: Double?
    let quality: QualityFlag
}

struct GlucoseInsight: Identifiable {
    let id = UUID()
    let date: Date
    let category: InsightCategory
    let summary: String
    let detail: String?
    let importance: InsightImportance
}

enum InsightCategory {
    case fastingGlucose
    case auc
    case recovery
    case variability
    case general
}

enum InsightImportance {
    case low, medium, high
}

enum GlucoseColor {
    case green, white, yellow, red
}


enum QualityFlag {
    case reliable
    case questionable
    case unreliable
}


