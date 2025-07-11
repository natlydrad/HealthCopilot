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

enum GlucoseColor {
    case green, white, yellow, red
}
