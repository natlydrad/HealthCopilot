import Foundation

class SyncManager {
    static let shared = SyncManager()
    private init() {}
    
    // Update this to your PocketBase instance (local IP while testing)
    private let baseURL = "http://<YOUR-MAC-IP>:8090/api/collections/meals/records"
    
    // Called from MealStore
    func syncMeals(_ meals: [Meal]) {
        for meal in meals where meal.pendingSync {
            uploadMeal(meal)
        }
    }
    
    // --- Create (POST) ---
    private func uploadMeal(_ meal: Meal) {
        guard let url = URL(string: baseURL) else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload: [String: Any] = [
            "id": meal.id.uuidString, // optional, PB also generates its own ID
            "text": meal.text,
            "timestamp": ISO8601DateFormatter().string(from: meal.timestamp)
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        
        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error = error {
                print("❌ Upload failed:", error)
                return
            }
            print("✅ Meal uploaded:", meal.text)
            DispatchQueue.main.async {
                MealStore.shared.markAsSynced(meal.id)
            }
        }.resume()
    }
    
    // --- Update (PATCH) ---
    func updateMeal(_ meal: Meal) {
        guard let url = URL(string: "\(baseURL)/\(meal.id.uuidString)") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload: [String: Any] = [
            "text": meal.text,
            "timestamp": ISO8601DateFormatter().string(from: meal.timestamp)
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        
        URLSession.shared.dataTask(with: request) { _, _, error in
            if let error = error {
                print("❌ Update failed:", error)
                return
            }
            print("✅ Meal updated:", meal.text)
            DispatchQueue.main.async {
                MealStore.shared.markAsSynced(meal.id)
            }
        }.resume()
    }
    
    // --- Delete (stub, you can wire later) ---
    func deleteMeal(id: UUID) {
        guard let url = URL(string: "\(baseURL)/\(id.uuidString)") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        
        URLSession.shared.dataTask(with: request) { _, _, error in
            if let error = error {
                print("❌ Delete failed:", error)
                return
            }
            print("✅ Meal deleted:", id)
        }.resume()
    }
}

