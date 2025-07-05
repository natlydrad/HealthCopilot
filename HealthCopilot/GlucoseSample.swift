//
//  GlucoseSample.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/5/25.
//

import Foundation
import HealthKit

struct GlucoseSample: Identifiable {
    let id = UUID()
    let date: Date
    let value: Double  // mg/dL
}
