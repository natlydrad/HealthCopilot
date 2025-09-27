import Foundation

struct Meal: Identifiable, Codable {
    let id: UUID
    var timestamp: Date
    var text: String
}

class MealStore: ObservableObject {
    @Published var meals: [Meal] = []
    private let fileName = "meals.json"
    
    init() {
        loadMeals()
    }
    
    func addMeal(text: String) {
        let newMeal = Meal(id: UUID(), timestamp: Date(), text: text)
        meals.append(newMeal)
        saveMeals()
    }
    
    func updateMeal(meal: Meal, newText: String, newDate: Date) {
        if let index = meals.firstIndex(where: { $0.id == meal.id }) {
            meals[index].text = newText
            meals[index].timestamp = newDate
            saveMeals()
        }
    }
    
    func deleteMeal(at offsets: IndexSet) {
        meals.remove(atOffsets: offsets)
        saveMeals()
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

