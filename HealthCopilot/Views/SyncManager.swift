import Foundation

class SyncManager {
    static let shared = SyncManager()
    private init() {}
    
    private let baseURL = "http://192.168.1.196:8090"
    private var token: String? {
        get { UserDefaults.standard.string(forKey: "PBToken") }
        set { UserDefaults.standard.setValue(newValue, forKey: "PBToken") }
    }
    private var userId: String? {
        get { UserDefaults.standard.string(forKey: "PBUserId") }
        set { UserDefaults.standard.setValue(newValue, forKey: "PBUserId") }
    }
    
    // MARK: - Login
    func login(email: String, password: String, completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "\(baseURL)/api/collections/users/auth-with-password") else {
            completion(false); return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload = ["identity": email, "password": password]
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        
        URLSession.shared.dataTask(with: request) { data, _, error in
            guard let data = data, error == nil else {
                completion(false); return
            }
            
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let token = json["token"] as? String,
               let record = json["record"] as? [String: Any],
               let id = record["id"] as? String {
                
                self.token = token
                self.userId = id
                print("✅ Logged in, userId: \(id)")
                completion(true)
            } else {
                print("❌ Login failed: \(String(data: data, encoding: .utf8) ?? "")")
                completion(false)
            }
        }.resume()
    }
    
    // MARK: - Create Meal
    func uploadMeal(_ meal: Meal) {
        guard let token = token, let userId = userId else {
            print("❌ No token, please login first")
            return
        }
        
        guard let url = URL(string: "\(baseURL)/api/collections/meals/records") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        
        let payload: [String: Any] = [
            "text": meal.text,
            "timestamp": ISO8601DateFormatter().string(from: meal.timestamp),
            "user": userId
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        
        URLSession.shared.dataTask(with: request) { data, _, error in
            if let error = error {
                print("❌ Upload error:", error)
                return
            }
            print("✅ Meal uploaded:", meal.text)
            DispatchQueue.main.async {
                MealStore.shared.markAsSynced(meal.id)
            }
        }.resume()
    }
    
    // TODO: add updateMeal + deleteMeal functions later
}

