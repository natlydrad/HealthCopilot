import Foundation

struct Meal: Identifiable, Codable {
    let id: UUID
    var timestamp: Date
    var text: String
    var pendingSync: Bool = true   // default to true until synced
}

class MealStore: ObservableObject {
    static let shared = MealStore()    // <--- NEW: global singleton
    
    @Published var meals: [Meal] = []
    private let fileName = "meals.json"
    
    init() {
        loadMeals()
    }
    
    // MARK: - CRUD
    
    func addMeal(text: String) {
        let newMeal = Meal(id: UUID(), timestamp: Date(), text: text)
        meals.append(newMeal)
        saveMeals()
        SyncManager.shared.syncMeals([newMeal])   // <--- NEW: try sync immediately
    }
    
    func updateMeal(meal: Meal, newText: String, newDate: Date) {
        if let index = meals.firstIndex(where: { $0.id == meal.id }) {
            meals[index].text = newText
            meals[index].timestamp = newDate
            meals[index].pendingSync = true   // <--- re-sync after edit
            saveMeals()
            SyncManager.shared.syncMeals([meals[index]])   // <--- try sync immediately
        }
    }
    
    func deleteMeal(at offsets: IndexSet) {
        let removedMeals = offsets.map { meals[$0] }
        meals.remove(atOffsets: offsets)
        saveMeals()
        // TODO: Send DELETE to PocketBase for each removedMeal.id
    }
    
    // Called by SyncManager when upload succeeds
    func markAsSynced(_ id: UUID) {
        if let index = meals.firstIndex(where: { $0.id == id }) {
            meals[index].pendingSync = false
            saveMeals()
        }
    }
    
    // MARK: - Persistence
    
    private func getFileURL() -> URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        return docs.appendingPathComponent(fileName)
    }
    
    func saveMeals() {
        let url = getFileURL()
        if let data = try? JSONEncoder().encode(meals) {
            try? data.write(to: url)
        }
    }
    
    private func loadMeals() {
        let url = getFileURL()
        if let data = try? Data(contentsOf: url),
           let decoded = try? JSONDecoder().decode([Meal].self, from: data) {
            meals = decoded
        }
    }
}

