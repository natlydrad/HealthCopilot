//
//  InsightGenerator.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/6/25.
//

import Foundation

struct MealInsight {
    let spikeTag: String
    let recoveryTag: String
    let personalComparisonTag: String
    let healthyRangeTag: String
    let optimalRangeTag: String
    let spikeValue: Double
    let recoveryMinutes: Int

    var prompt: String {
        return """
        Analyze this meal factually without giving any advice or suggestions:
        - Meal: [Meal Description Here]
        - Spike: +\(Double(spikeValue)) mg/dL → \(spikeTag)
        - Recovery Time: \(recoveryMinutes) minutes → \(recoveryTag)
        - Compared to usual: \(personalComparisonTag)
        - Healthy Range: \(healthyRangeTag)
        - Optimal Range: \(optimalRangeTag)

        Provide 2 sentences summarizing this glucose response.
        """
    }
}

class InsightGenerator {

    static func generateTags(for spike: Double, recoveryMinutes: Int, percentile: Double) -> MealInsight {

        // Spike Tag
        let spikeTag: String
        switch spike {
        case 0..<20: spikeTag = "Minimal"
        case 20..<40: spikeTag = "Moderate"
        case 40..<60: spikeTag = "High"
        default: spikeTag = "Very High"
        }

        // Recovery Tag
        let recoveryTag: String
        switch recoveryMinutes {
        case ..<60: recoveryTag = "Fast"
        case 60..<120: recoveryTag = "Normal"
        case 120..<180: recoveryTag = "Slow"
        default: recoveryTag = "Very Slow"
        }

        // Personal Comparison Tag
        let personalComparisonTag: String
        switch percentile {
        case ..<33: personalComparisonTag = "Lower than Usual"
        case 33..<66: personalComparisonTag = "About Average"
        default: personalComparisonTag = "Higher than Usual"
        }

        // Healthy Range Tag
        let healthyRangeTag = spike <= 30 ? "Within Healthy Range" : "Above Healthy Range"

        // Optimal Range Tag
        let optimalRangeTag = spike <= 20 ? "Within Optimal Range" : "Above Optimal Range"

        return MealInsight(
            spikeTag: spikeTag,
            recoveryTag: recoveryTag,
            personalComparisonTag: personalComparisonTag,
            healthyRangeTag: healthyRangeTag,
            optimalRangeTag: optimalRangeTag,
            spikeValue: spike,
            recoveryMinutes: recoveryMinutes
        )
    }

}
