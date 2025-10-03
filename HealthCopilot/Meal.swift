// Meal.swift
import Foundation

struct Meal: Identifiable, Codable {
    var pbId: String?
    var localId: String
    var text: String
    var timestamp: Date
    var pendingSync: Bool = false
    var updatedAt: Date?
    var id: String { localId }
    var isDeleted: Bool = false
    var photo: String? = nil

    enum CodingKeys: String, CodingKey {
        case pbId       = "id"
        case localId
        case text
        case timestamp
        case pendingSync
        case updatedAt  = "updated"
        case isDeleted
        case photo                  // local JSON uses "photo"
        case image                  // PB uses "image"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.pbId        = try? c.decode(String.self, forKey: .pbId)
        self.localId     = try c.decode(String.self, forKey: .localId)
        self.text        = try c.decode(String.self, forKey: .text)
        self.timestamp   = try c.decode(Date.self, forKey: .timestamp)
        self.updatedAt   = try? c.decode(Date.self, forKey: .updatedAt)
        self.pendingSync = (try? c.decodeIfPresent(Bool.self, forKey: .pendingSync)) ?? false
        self.isDeleted   = (try? c.decodeIfPresent(Bool.self, forKey: .isDeleted)) ?? false

        // Accept either "photo" (local file) or "image" (PocketBase)
        self.photo = (try? c.decodeIfPresent(String.self, forKey: .photo))
                  ?? (try? c.decodeIfPresent(String.self, forKey: .image))
    }

    // Keep local saves backward-compatible: write "photo" in meals.json (not "image")
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(pbId, forKey: .pbId)
        try c.encode(localId, forKey: .localId)
        try c.encode(text, forKey: .text)
        try c.encode(timestamp, forKey: .timestamp)
        try c.encodeIfPresent(updatedAt, forKey: .updatedAt)
        try c.encode(pendingSync, forKey: .pendingSync)
        try c.encode(isDeleted, forKey: .isDeleted)
        try c.encodeIfPresent(photo, forKey: .photo)   // ← only "photo" for local storage
    }

    init(text: String, timestamp: Date) {
        self.pbId = nil
        self.localId = UUID().uuidString
        self.text = text
        self.timestamp = timestamp
        self.pendingSync = true
        self.updatedAt = Date()
    }
}
