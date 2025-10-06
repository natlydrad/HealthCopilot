import Foundation

struct RawInput: Codable, Identifiable, Equatable {
    var localId: String = UUID().uuidString.uppercased()
    var id: String?                 // PocketBase id
    var user: String                // same as logged-in user id
    var timestamp: Date = Date()
    var text: String = ""
    var status: String = "pending"  // pending / parsed / error
    var parsedAt: Date? = nil
    var pendingSync: Bool = true
    var updatedAt: Date = Date()
}

final class RawInputStore: ObservableObject {
    static let shared = RawInputStore()
    @Published var items: [RawInput] = []

    private let fileURL: URL = {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        return docs.appendingPathComponent("raw_inputs.json")
    }()

    private init() { load() }

    func load() {
        if let data = try? Data(contentsOf: fileURL),
           let decoded = try? JSONDecoder().decode([RawInput].self, from: data) {
            self.items = decoded
        }
    }

    func save() {
        if let data = try? JSONEncoder().encode(items) {
            try? data.write(to: fileURL)
        }
    }

    func add(text: String, userId: String) {
        var r = RawInput(user: userId, text: text)
        r.status = "pending"
        r.pendingSync = true
        items.insert(r, at: 0)
        save()
        SyncManager.shared.pushRawInputs()   // added in step 2
    }

    func edit(localId: String, newText: String) {
        guard let idx = items.firstIndex(where: { $0.localId == localId }) else { return }
        items[idx].text = newText
        items[idx].status = "pending"
        items[idx].pendingSync = true
        items[idx].updatedAt = Date()
        save()
        SyncManager.shared.pushRawInputs()
    }
}
