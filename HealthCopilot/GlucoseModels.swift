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

struct AUCResult {
    let date: Date
    let value: Double
    let quality: QualityFlag  // same enum as FastingGlucoseResult
}


struct GlucoseInsight: Identifiable {
    let id = UUID()
    let date: Date
    let category: InsightCategory
    let summary: String // "Fasting glucose dropped"
    let detail: String? // Trend description (moved into expandable)
    let importance: InsightImportance
    let mathStats: GlucoseMathStats?
    let timeSpanLabel: String // "Last 3 days"
}

struct TimeRangeInsights: Identifiable {
    let id = UUID()
    let dayCount: Int // like 3, 7, 14, 90
    let range: String // e.g. "Last 14 days"
    let fastingInsight: GlucoseInsight?
    let aucInsight: GlucoseInsight?
}



struct GlucoseMathStats {
    let slope: Double
    let rSquared: Double
    let start: Int
    let end: Int
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


