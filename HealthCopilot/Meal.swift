// Meal.swift
import Foundation

struct Meal: Identifiable, Codable {
    // PB identity (optional until first upload)
    var pbId: String?          // maps from "id" in PB

    // Stable local identity
    var localId: String        // created once on device

    // Content
    var text: String
    var timestamp: Date

    // Sync metadata (LOCAL ONLY)
    var pendingSync: Bool = false   // default false; not decoded/encoded to PB
    var updatedAt: Date?            // mirrors PB "updated" (optional for now)

    // SwiftUI identity
    var id: String { localId }

    enum CodingKeys: String, CodingKey {
        case pbId      = "id"
        case localId
        case text
        case timestamp
        case updatedAt = "updated"
        // NOTE: no "pendingSync" here on purpose
        
    }
}

extension Meal {
    /// Create a brand-new local meal (no PB id yet)
    init(text: String, timestamp: Date) {
        self.pbId = nil
        self.localId = UUID().uuidString
        self.text = text
        self.timestamp = timestamp
        self.pendingSync = true          // needs upload
        self.updatedAt = Date()          // last writer wins; local now
    }
}
