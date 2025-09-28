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


    
    // Tombstone delete
    func deleteMeal(at offsets: IndexSet) {
        var changed = false
        for index in offsets {
            var m = meals[index]
            if let _ = m.pbId {
                // server knows this record → tombstone & queue
                m.isDeleted = true
                m.pendingSync = true
                m.updatedAt = Date()
                meals[index] = m
                changed = true
            } else {
                // never uploaded → just remove locally
                meals.remove(at: index)
                changed = true
            }
        }
        if changed {
            saveMeals()
            SyncManager.shared.pushDirty()
        }
    }
    
    // MARK: - Delete / Tombstone

    /// User-initiated delete from UI (can be offline).
    /// We DO NOT remove from the array yet — we tombstone & queue a sync.
    func deleteMeals(withLocalIds ids: [String]) {
        var changed = false
        for id in ids {
            if let idx = meals.firstIndex(where: { $0.localId == id }) {
                if meals[idx].isDeleted == false {
                    meals[idx].isDeleted = true
                    meals[idx].pendingSync = true
                    meals[idx].updatedAt = Date()   // local becomes latest writer
                    changed = true
                }
            }
        }
        if changed {
            saveMeals()
            // optional: kick a push right away
            SyncManager.shared.pushDirty()
        }
    }

    /// Called by SyncManager after a successful server DELETE (2xx or 404).
    /// Now we physically remove it from disk+memory.
    func remove(localId: String) {
        if let idx = meals.firstIndex(where: { $0.localId == localId }) {
            meals.remove(at: idx)
            saveMeals()
        }
    }

    /// Called by SyncManager after a successful POST/PATCH.
    func markSynced(localId: String) {
        if let idx = meals.firstIndex(where: { $0.localId == localId }) {
            meals[idx].pendingSync = false
            meals[idx].updatedAt = Date()
            saveMeals()
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

        // Fast lookup by localId for local records
        var byLocal = Dictionary(uniqueKeysWithValues: meals.map { ($0.localId, $0) })

        for server in remote {
            if var local = byLocal[server.localId] {

                // 🔒 Tombstone protection: if we have a local tombstone,
                // NEVER let a server row overwrite or clear its pending delete.
                if local.isDeleted {
                    // Keep the delete + keep pendingSync so the delete will still push
                    byLocal[server.localId] = local
                    continue
                }

                // Last-writer-wins, but only for non-deleted local rows
                let localUpdated  = age(local.updatedAt)
                let serverUpdated = age(server.updatedAt)

                if serverUpdated > localUpdated {
                    // Server wins → take fields; clear pendingSync (only because it's not deleted)
                    local.pbId        = server.pbId ?? local.pbId
                    local.text        = server.text
                    local.timestamp   = server.timestamp
                    local.updatedAt   = server.updatedAt
                    local.pendingSync = false
                    // Never copy any server-side "deleted" state into local;
                    // PocketBase doesn't usually return hard-deleted rows anyway.
                    byLocal[server.localId] = local
                } else {
                    // Local wins → keep as-is (pendingSync stays true if dirty)
                    byLocal[server.localId] = local
                }

            } else {
                // New to device → accept server row (not deleted)
                var fresh = server
                // If your API ever returns server-side soft-deleted rows, skip them:
                if fresh.isDeleted { continue }
                fresh.pendingSync = false
                byLocal[server.localId] = fresh
            }
        }

        // Build array, drop local tombstones from the visible list,
        // and stabilize ordering by (timestamp, then updatedAt)
        meals = Array(byLocal.values)
            .filter { !$0.isDeleted }
            .sorted { a, b in
                if a.timestamp != b.timestamp { return a.timestamp > b.timestamp }
                return age(a.updatedAt) > age(b.updatedAt)
            }

        print("🔗 mergeFetched: local(after)=\(meals.count)")
        saveMeals()
    }


}
