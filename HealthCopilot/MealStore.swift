import Foundation

class MealStore: ObservableObject {
    static let shared = MealStore()
    
    @Published var meals: [Meal] = []
    private let fileName = "meals.json"
    
    init() { loadMeals() }
    
    // Add
    func addMeal(text: String, at date: Date = Date()) {
        let newMeal = Meal(text: text, timestamp: date)   // ← now compiles
        meals.append(newMeal)
        saveMeals()
        SyncManager.shared.uploadMeal(newMeal)            // (or upsert)
    }
    
    // Update
    func updateMeal(meal: Meal, newText: String, newDate: Date) {
        if let i = meals.firstIndex(where: { $0.localId == meal.localId }) {
            meals[i].text = newText
            meals[i].timestamp = newDate
            meals[i].pendingSync = true
            meals[i].updatedAt = Date()   // ← important
            saveMeals()

            var updated = meals[i]
            SyncManager.shared.uploadMeal(updated)  // or upsert/update path
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
    
    // Merge fetched → print before/after
    func mergeFetched(_ remote: [Meal]) {
        print("🔗 mergeFetched: remote=\(remote.count) local(before)=\(meals.count)")
        var byLocal: [String: Meal] = [:]
        meals.forEach { byLocal[$0.localId] = $0 }
        
        for r in remote {
            if var existing = byLocal[r.localId] {
                existing.pbId = r.pbId ?? existing.pbId
                existing.text = r.text
                existing.timestamp = r.timestamp
                existing.pendingSync = false
                byLocal[r.localId] = existing
            } else {
                byLocal[r.localId] = r
            }
        }
        
        meals = Array(byLocal.values).sorted(by: { $0.timestamp > $1.timestamp })
        print("🔗 mergeFetched: local(after)=\(meals.count)")
        saveMeals()
    }
}
