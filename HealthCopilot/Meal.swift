import Foundation

struct Meal: Identifiable, Codable {
    // SwiftUI identity = localId
    var id: String { localId }

    // PocketBase record id (nil until synced)
    var pbId: String?

    // Stable local identity we generate once and never change
    var localId: String

    var timestamp: Date
    var text: String
    var pendingSync: Bool = true

    init(
        pbId: String? = nil,
        localId: String = UUID().uuidString,
        timestamp: Date,
        text: String,
        pendingSync: Bool = true
    ) {
        self.pbId = pbId
        self.localId = localId
        self.timestamp = timestamp
        self.text = text
        self.pendingSync = pendingSync
    }

    // Map PocketBase "id" <-> pbId while keeping localId as-is
    enum CodingKeys: String, CodingKey {
        case pbId = "id"
        case localId
        case timestamp
        case text
        case pendingSync
    }
}
