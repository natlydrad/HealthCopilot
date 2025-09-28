// Meal.swift
import Foundation

struct Meal: Identifiable, Codable {
    var pbId: String?
    var localId: String
    var text: String
    var timestamp: Date
    var pendingSync: Bool = false         // local-only flag, should persist locally
    var updatedAt: Date?                  // PB 'updated' mirror
    var id: String { localId }
    var isDeleted: Bool = false

    enum CodingKeys: String, CodingKey {
        case pbId       = "id"
        case localId
        case text
        case timestamp
        case pendingSync                    // ⬅️ include so we save it locally
        case updatedAt  = "updated"
        case isDeleted
    }

    // Custom decode: PB won’t send pendingSync, so default it to false
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.pbId       = try? c.decode(String.self, forKey: .pbId)
        self.localId    = try c.decode(String.self, forKey: .localId)
        self.text       = try c.decode(String.self, forKey: .text)
        self.timestamp  = try c.decode(Date.self, forKey: .timestamp)
        self.updatedAt  = try? c.decode(Date.self, forKey: .updatedAt)
        self.pendingSync = (try? c.decodeIfPresent(Bool.self, forKey: .pendingSync)) ?? false
        self.isDeleted   = (try? c.decodeIfPresent(Bool.self, forKey: .isDeleted)) ?? false
    }

    // Synthesized encode is fine (it will include pendingSync via CodingKeys)
}

extension Meal {
    /// Full designated initializer (so you still have a memberwise-style init)
    init(pbId: String? = nil,
         localId: String,
         text: String,
         timestamp: Date,
         pendingSync: Bool = false,
         updatedAt: Date? = nil) {
        self.pbId = pbId
        self.localId = localId
        self.text = text
        self.timestamp = timestamp
        self.pendingSync = pendingSync
        self.updatedAt = updatedAt
    }

    /// Convenience initializer for creating a brand-new local meal
    init(text: String, timestamp: Date) {
        self.pbId = nil
        self.localId = UUID().uuidString
        self.text = text
        self.timestamp = timestamp
        self.pendingSync = true          // new local records start dirty
        self.updatedAt = Date()          // local just wrote
    }
}
