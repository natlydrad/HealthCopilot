import Foundation

class MealStore: ObservableObject {
    static let shared = MealStore()
    
    @Published var meals: [Meal] = []
    private let fileName = "meals.json"
    
    init() { loadMeals() }
    
    // Add
    func addMeal(text: String, at date: Date = Date()) {
        var newMeal = Meal(text: text, timestamp: date)
        newMeal.pendingSync = true
        newMeal.updatedAt = Date()              // 👈 local is now the latest writer
        meals.append(newMeal)
        saveMeals()
        SyncManager.shared.pushDirty()
    }
    
    // Update
    func updateMeal(meal: Meal, newText: String, newDate: Date) {
        if let i = meals.firstIndex(where: { $0.localId == meal.localId }) {
            meals[i].text = newText
            meals[i].timestamp = newDate
            meals[i].pendingSync = true
            meals[i].updatedAt = Date()   // ← important
            saveMeals()

            SyncManager.shared.pushDirty()  // or upsert/update path
        }
    }

    
    
    
    // Delete
    func deleteMeal(at offsets: IndexSet) {
        let removed = offsets.map { meals[$0] }
        meals.remove(atOffsets: offsets)
        saveMeals()
        removed.forEach { m in
            if let _ = m.pbId {
                SyncManager.shared.deleteMeal(m)
            }
        }
    }
    
    // Link PB id into the existing local meal (called after POST succeeds)
    func linkLocalToRemote(localId: String, pbId: String) {
        if let i = meals.firstIndex(where: { $0.localId == localId }) {
            meals[i].pbId = pbId
            saveMeals()
            objectWillChange.send()
        }
    }
    
    func markSynced(localId: String) {
        if let i = meals.firstIndex(where: { $0.localId == localId }) {
            meals[i].pendingSync = false
            saveMeals()
            objectWillChange.send()
        }
    }
    
    func markClean(localId: String) {
        if let i = meals.firstIndex(where: { $0.localId == localId }) {
            meals[i].pendingSync = false
            saveMeals()
            print("✅ Marked clean:", localId)
        }
    }
    
    // Merge fetched server meals by localId (don’t duplicate, don’t lose local)
    private func getFileURL() -> URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        return docs.appendingPathComponent(fileName)
    }
    
    func saveMeals() {
        let url = getFileURL()
        do {
            let data = try JSONEncoder().encode(meals)
            try data.write(to: url)
            print("💾 Saved \(meals.count) meals to:", url.path)
        } catch {
            print("❌ saveMeals error:", error)
        }
    }
    
    private func loadMeals() {
        let url = getFileURL()
        if let data = try? Data(contentsOf: url),
           let decoded = try? JSONDecoder().decode([Meal].self, from: data) {
            meals = decoded
            print("📂 Loaded \(meals.count) meals from:", url.path)
        } else {
            print("📂 No existing meals file at:", url.path)
        }
    }
    
    /// Helper: treat nil as very old for comparisons.
    private func age(_ d: Date?) -> Date {
        d ?? .distantPast
    }

    func mergeFetched(_ remote: [Meal]) {
        print("🔗 mergeFetched: remote=\(remote.count) local(before)=\(meals.count)")

        // Build quick lookup by localId
        var byLocal = Dictionary(uniqueKeysWithValues: meals.map { ($0.localId, $0) })

        for server in remote {
            if var local = byLocal[server.localId] {
                // Compare "last writer"
                let localUpdated  = age(local.updatedAt)
                let serverUpdated = age(server.updatedAt)

                if serverUpdated > localUpdated {
                    // Server wins → take server fields; clear pendingSync
                    local.pbId       = server.pbId ?? local.pbId
                    local.text       = server.text
                    local.timestamp  = server.timestamp
                    local.updatedAt  = server.updatedAt
                    local.pendingSync = false
                    byLocal[server.localId] = local
                } else {
                    // Local wins → keep local as-is (still pendingSync = true if dirty)
                    // no change needed
                }
            } else {
                // New to device → accept server row
                var fresh = server
                fresh.pendingSync = false
                byLocal[server.localId] = fresh
            }
        }

        // Commit back to array (keep your preferred sort)
        meals = Array(byLocal.values).sorted(by: { $0.timestamp > $1.timestamp })

        print("🔗 mergeFetched: local(after)=\(meals.count)")
        saveMeals()
    }

}
