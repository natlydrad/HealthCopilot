import Foundation

private let pbDateFormatterMS: DateFormatter = {
    let df = DateFormatter()
    df.locale = Locale(identifier: "en_US_POSIX")
    df.timeZone = TimeZone(secondsFromGMT: 0)
    df.dateFormat = "yyyy-MM-dd HH:mm:ss.SSSXXXXX"  // PB with ms
    return df
}()

private let pbDateFormatter: DateFormatter = {
    let df = DateFormatter()
    df.locale = Locale(identifier: "en_US_POSIX")
    df.timeZone = TimeZone(secondsFromGMT: 0)
    df.dateFormat = "yyyy-MM-dd HH:mm:ssXXXXX"      // PB without ms
    return df
}()

private let isoTFormatter: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
}()

private func parsePBDate(_ s: String) -> Date? {
    // Try "yyyy-MM-dd HH:mm:ss.SSSXXXXX" and "...ssXXXXX"
    if let d = pbDateFormatterMS.date(from: s) ?? pbDateFormatter.date(from: s) {
        return d
    }
    // Accept ISO by swapping space → "T"
    let isoLike = s.replacingOccurrences(of: " ", with: "T")
    if let d = isoTFormatter.date(from: isoLike) { return d }

    // Fallbacks that treat 'Z' as a literal
    let fmts = [
        "yyyy-MM-dd HH:mm:ss.SSS'Z'",
        "yyyy-MM-dd HH:mm:ss'Z'",
        "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
        "yyyy-MM-dd'T'HH:mm:ss'Z'"
    ]
    let df = DateFormatter()
    df.locale = Locale(identifier: "en_US_POSIX")
    df.timeZone = TimeZone(secondsFromGMT: 0)
    for f in fmts {
        df.dateFormat = f
        if let d = df.date(from: s) { return d }
        if let d = df.date(from: isoLike) { return d }
    }
    return nil
}


class SyncManager {
    static let shared = SyncManager()
    private init() {}
    
    private let baseURL = "http://192.168.1.196:8090"
    
    private var token: String? {
        get { UserDefaults.standard.string(forKey: "PBToken") }
        set { UserDefaults.standard.setValue(newValue, forKey: "PBToken") }
    }
    var userId: String? {
        get { UserDefaults.standard.string(forKey: "PBUserId") }
        set { UserDefaults.standard.setValue(newValue, forKey: "PBUserId") }
    }
    
    // Login (unchanged)
    func login(email: String, password: String, completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "\(baseURL)/api/collections/users/auth-with-password") else {
            completion(false); return
        }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["identity": email, "password": password])
        
        URLSession.shared.dataTask(with: req) { data, _, err in
            guard let data = data, err == nil else { completion(false); return }
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let token = json["token"] as? String,
               let record = json["record"] as? [String: Any],
               let id = record["id"] as? String {
                self.token = token
                self.userId = id
                print("✅ Logged in, userId:", id)
                completion(true)
            } else {
                print("❌ Login failed:", String(data: data, encoding: .utf8) ?? "")
                completion(false)
            }
        }.resume()
    }
    
    // Create (POST)
    func uploadMeal(_ meal: Meal) {
        guard let token = token, let userId = userId else {
            print("❌ No token or user"); return
        }
        guard let url = URL(string: "\(baseURL)/api/collections/meals/records") else { return }
        
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.httpBody = try? JSONSerialization.data(withJSONObject: [
            "text": meal.text,
            "timestamp": ISO8601DateFormatter().string(from: meal.timestamp),
            "localId": meal.localId,
            "user": userId
        ])
        
        URLSession.shared.dataTask(with: req) { data, resp, err in
            if let err = err { print("❌ Upload error:", err); return }
            
            let status = (resp as? HTTPURLResponse)?.statusCode ?? -1
            if status == 400, let data = data {
                // likely unique(localId) violation → fetch by localId, link, then PATCH latest values
                print("⚠️ POST 400; trying resolve by localId. Resp:", String(data: data, encoding: .utf8) ?? "")
                self.findByLocalId(meal.localId) { pbId in
                    guard let pbId else { return }
                    DispatchQueue.main.async {
                        MealStore.shared.linkLocalToRemote(localId: meal.localId, pbId: pbId)
                        // push current fields so server matches the phone
                        self.updateMeal(meal)
                    }
                }
                return
            }
            
            guard let data = data else { return }
            print("📦 Upload response:", String(data: data, encoding: .utf8) ?? "")
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let pbId = json["id"] as? String,
               let returnedLocal = json["localId"] as? String {
                DispatchQueue.main.async {
                    MealStore.shared.linkLocalToRemote(localId: returnedLocal, pbId: pbId)
                    // ✅ Add this line so the "unsynced" chip clears after a successful POST
                    MealStore.shared.markSynced(localId: returnedLocal)
                }
            }
        }.resume()
        
        
    }
    
    
    // Update (PATCH)
    // PATCH existing record; if pbId is missing, resolve by localId first
    func updateMeal(_ meal: Meal) {
        guard let token = token else {
            print("❌ No token"); return
        }

        // If pbId is missing, try to resolve it, then recurse into PATCH
        guard let pbId = meal.pbId else {
            findByLocalId(meal.localId) { found in
                if let found = found {
                    DispatchQueue.main.async {
                        MealStore.shared.linkLocalToRemote(localId: meal.localId, pbId: found)
                        var patched = meal
                        patched.pbId = found
                        self.updateMeal(patched)
                    }
                } else {
                    // Not on server yet → create and then we'll be linked
                    self.uploadMeal(meal)
                }
            }
            return
        }

        guard let url = URL(string: "\(baseURL)/api/collections/meals/records/\(pbId)") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "PATCH"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.httpBody = try? JSONSerialization.data(withJSONObject: [
            "text": meal.text,
            "timestamp": ISO8601DateFormatter().string(from: meal.timestamp)
        ])

        URLSession.shared.dataTask(with: req) { data, resp, err in
            if let err = err { print("⚠️ Update error:", err); return }
            let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
            print("🔄 Update status:", code)
            if code >= 200 && code < 300 {
                // Success: clear pendingSync so "unsynced" chip disappears
                DispatchQueue.main.async {
                    MealStore.shared.markSynced(localId: meal.localId)
                }
            } else if let data = data {
                print("⚠️ Update failed body:", String(data: data, encoding: .utf8) ?? "")
            }
        }.resume()
    }

    
    // Upsert: PATCH if we know pbId; else resolve by localId; else POST
    func upsertMeal(_ meal: Meal) {
        if let _ = meal.pbId {
            self.updateMeal(meal)
            return
        }
        self.findByLocalId(meal.localId) { pbId in
            if let pbId = pbId {
                DispatchQueue.main.async {
                    MealStore.shared.linkLocalToRemote(localId: meal.localId, pbId: pbId)
                    self.updateMeal(meal) // now we can PATCH with current fields
                }
            } else {
                self.uploadMeal(meal) // create it for the first time
            }
        }
    }
    
    
    // Delete
    func deleteMeal(_ meal: Meal) {
        guard let token = token, let pbId = meal.pbId else {
            print("❌ No token or pbId, cannot delete"); return
        }
        guard let url = URL(string: "\(baseURL)/api/collections/meals/records/\(pbId)") else { return }
        
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        
        URLSession.shared.dataTask(with: req) { _, resp, err in
            if let err = err { print("❌ Delete error:", err); return }
            let status = (resp as? HTTPURLResponse)?.statusCode ?? -1
            print("🔄 Delete status:", status)
        }.resume()
    }
    
    // Fetch & merge
    func fetchMeals() {
        guard let token = token, let userId = userId else {
            print("❌ fetchMeals: missing token/userId"); return
        }

        let raw = "filter=" + "user='\(userId)'"
        let qs  = raw.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? raw
        guard let url = URL(string: "\(baseURL)/api/collections/meals/records?\(qs)&sort=-created") else { return }

        print("🌐 GET \(url.absoluteString)")

        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        URLSession.shared.dataTask(with: req) { data, resp, err in
            if let err = err {
                print("❌ fetchMeals network error:", err)
                return
            }
            let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
            print("📥 fetchMeals HTTP status:", code)

            guard let data = data else { print("❌ fetchMeals: no data"); return }

            // Log raw length (optional: dump string if needed)
            print("📦 fetchMeals bytes:", data.count)

            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .custom { dec in
                let c = try dec.singleValueContainer()
                let s = try c.decode(String.self)
                if let d = parsePBDate(s) { return d }
                print("❌ Bad date string from PB:", s)   // <-- will show exact string
                throw DecodingError.dataCorruptedError(in: c, debugDescription: "Unparsable date: \(s)")
            }

            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let items = json["items"] as? [[String: Any]] {

                print("🧮 fetchMeals items count:", items.count)

                var decoded: [Meal] = []
                for (idx, obj) in items.enumerated() {
                    do {
                        // quick pre-checks for missing keys we require
                        if obj["localId"] == nil {
                            print("⚠️ [\(idx)] skipping: missing localId. Raw:", obj)
                            continue
                        }
                        if obj["timestamp"] == nil {
                            print("⚠️ [\(idx)] skipping: missing timestamp. Raw:", obj)
                            continue
                        }

                        let raw = try JSONSerialization.data(withJSONObject: obj)
                        let m = try decoder.decode(Meal.self, from: raw)
                        decoded.append(m)
                    } catch {
                        print("❌ [\(idx)] decode error:", error)
                        print("   Raw item:", obj)
                    }
                }

                print("✅ Decoded meals:", decoded.count)
                DispatchQueue.main.async {
                    MealStore.shared.mergeFetched(decoded)
                }
            } else {
                print("❌ fetchMeals: JSON parse failed. Body:",
                      String(data: data, encoding: .utf8) ?? "<non-utf8>")
            }

        }.resume()
    }

    
    
    // Helper: find record id by localId
    private func findByLocalId(_ localId: String, completion: @escaping (String?) -> Void) {
        guard let token = token else { completion(nil); return }
        let raw = "filter=" + "localId='\(localId)'"
        let qs  = raw.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? raw
        guard let url = URL(string: "\(baseURL)/api/collections/meals/records?\(qs)&perPage=1") else {
            completion(nil); return
        }
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        
        URLSession.shared.dataTask(with: req) { data, _, err in
            guard let data = data, err == nil else { completion(nil); return }
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let items = json["items"] as? [[String: Any]],
               let first = items.first,
               let pbId = first["id"] as? String {
                completion(pbId)
            } else {
                completion(nil)
            }
        }.resume()
    }
}
