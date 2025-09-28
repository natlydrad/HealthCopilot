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

    // MARK: - Push everything dirty (deletes first)
    func pushDirty() {
        // Grab a snapshot so we don’t mutate while iterating
        let all = MealStore.shared.meals

        // 1) Deletes (tombstoned items)
        let deletes = all.filter { $0.isDeleted }
        // 2) Upserts (dirty but not deleted)
        let upserts = all.filter { $0.pendingSync && $0.isDeleted == false }

        print("🚚 pushDirty: \(deletes.count) deletes, \(upserts.count) upserts")

        // --- Deletes first so we never resurrect a row on fetch ---
        for m in deletes {
            deleteMealAsync(m)
        }
        // Then upserts
        for m in upserts {
            if m.pbId == nil {
                upsertMeal(m)
            } else {
                updateMeal(m)
            }
        }
    }


    
    // One-time reconciliation: link existing PB records and mark the rest pending.
    func reconcileLocalWithServer() {
        guard let token = token, let userId = userId else {
            print("⛔️ reconcile: not logged in"); return
        }

        // Fetch ALL server meals for this user (no delta so we see everything)
        let raw = "filter=" + "user='\(userId)'"
        let qs  = raw.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? raw
        guard let url = URL(string: "\(baseURL)/api/collections/meals/records?\(qs)&perPage=200") else { return }

        print("🧭 reconcile: GET \(url.absoluteString)")

        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        URLSession.shared.dataTask(with: req) { data, resp, err in
            if let err = err { print("❌ reconcile fetch error:", err); return }
            guard let data = data else { print("❌ reconcile: no data"); return }

            // Parse raw JSON to build a map of localId -> (id, updated)
            var serverByLocalId: [String: (id: String, updated: Date?)] = [:]

            if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let items = obj["items"] as? [[String: Any]] {
                for it in items {
                    if let lid = it["localId"] as? String,
                       let id  = it["id"] as? String {
                        let s = it["updated"] as? String
                        let updated = parsePBDate(s ?? "")
                        serverByLocalId[lid] = (id: id, updated: updated)
                    }
                }
                print("🧭 reconcile: server items =", serverByLocalId.count)
            } else {
                print("❌ reconcile: JSON parse failed:",
                      String(data: data, encoding: .utf8) ?? "<non-utf8>")
                return
            }

            // Walk local meals
            var changed = false
            for i in 0..<MealStore.shared.meals.count {
                var m = MealStore.shared.meals[i]

                // Case A: local has no pbId
                if m.pbId == nil {
                    if let srv = serverByLocalId[m.localId] {
                        // Found on server → link pbId and adopt server 'updated' if newer
                        m.pbId = srv.id
                        if let su = srv.updated, su > (m.updatedAt ?? .distantPast) {
                            m.updatedAt = su
                        }
                        // If content differs and local is newer, leave pending to PATCH
                        // Else mark clean
                        // (We don't compare text here to keep it simple—Stage 2 will handle conflicts.)
                        m.pendingSync = false
                        MealStore.shared.meals[i] = m
                        changed = true
                        print("🔗 reconcile linked:", m.localId, "→", srv.id)
                    } else {
                        // Not on server → mark pending so queue will POST it
                        if m.pendingSync == false {
                            m.pendingSync = true
                            // Keep or bump updatedAt so local is considered newer
                            if m.updatedAt == nil { m.updatedAt = Date() }
                            MealStore.shared.meals[i] = m
                            changed = true
                            print("🟥 reconcile marked pending:", m.localId)
                        }
                    }
                } else {
                    // Case B: local has pbId — optionally verify it still exists on server
                    // If it doesn't, flip to pending so we recreate (rare; e.g., server deletion).
                    if serverByLocalId[m.localId] == nil {
                        m.pendingSync = true
                        MealStore.shared.meals[i] = m
                        changed = true
                        print("🟧 reconcile: pbId set but not on server, will re-push:", m.localId)
                    }
                }
            }

            if changed {
                MealStore.shared.saveMeals()
            }

            // Finally, run the queue
            DispatchQueue.main.async {
                self.pushDirty()
            }
        }.resume()
    }

    // MARK: - DELETE (idempotent)
    private func deleteMealAsync(_ meal: Meal) {
        guard let token = token else { return }

        // If we don’t know pbId yet, resolve it by localId (once online)
        func resolveAndDelete(by localId: String) {
            findPbId(forLocalId: localId) { pbId in
                guard let pbId = pbId else {
                    print("🗑️ DELETE noop (404): \(localId)")
                    // Treat as success and purge locally
                    MealStore.shared.remove(localId: localId)
                    return
                }
                self.performDelete(pbId: pbId, localId: localId)
            }
        }

        if let pbId = meal.pbId {
            performDelete(pbId: pbId, localId: meal.localId)
        } else {
            resolveAndDelete(by: meal.localId)
        }
    }
    
    // Resolve PocketBase id from our stable localId + user filter
    private func findPbId(forLocalId localId: String,
                          completion: @escaping (String?) -> Void) {
        guard let token = token else { completion(nil); return }

        // if you keep userId on SyncManager, include it (safer & faster)
        let userFilter: String
        if let userId = self.userId, !userId.isEmpty {
            userFilter = "user='\(userId)' && localId='\(localId)'"
        } else {
            userFilter = "localId='\(localId)'"
        }

        // URL-encode filter
        let allowed = CharacterSet.urlQueryAllowed
        let encodedFilter = userFilter.addingPercentEncoding(withAllowedCharacters: allowed) ?? userFilter

        // perPage=1 is enough because localId should be unique in PB
        let url = URL(string: "\(baseURL)/api/collections/meals/records?filter=\(encodedFilter)&perPage=1")!
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        URLSession.shared.dataTask(with: req) { data, _, err in
            guard err == nil, let data = data else { completion(nil); return }
            // Minimal decode: items[0].id
            struct ListResp: Decodable { struct Item: Decodable { let id: String }
                let items: [Item] }
            if let r = try? JSONDecoder().decode(ListResp.self, from: data),
               let first = r.items.first {
                completion(first.id)
            } else {
                completion(nil)
            }
        }.resume()
    }


    private func performDelete(pbId: String, localId: String) {
        guard let token = token else { return }
        let url = URL(string: "\(baseURL)/api/collections/meals/records/\(pbId)")!
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        URLSession.shared.dataTask(with: req) { _, resp, err in
            if let err = err {
                print("⏳ delete retry later: \(localId) \(err.localizedDescription)")
                return
            }
            let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
            if (200..<300).contains(code) || code == 404 {
                print("🗑️ DELETE ok: \(localId)")
                // Now we may purge the local row
                DispatchQueue.main.async {
                    MealStore.shared.remove(localId: localId)
                }
            } else {
                print("⏳ delete retry later: \(localId) HTTP \(code)")
            }
        }.resume()
    }



    /// Async upsert-by-localId (POST → fallback to PATCH)
    private func upsertMealAsync(_ meal: Meal) async throws {
        guard let token = token else { throw URLError(.userAuthenticationRequired) }

        // 1) If we already have pbId, just PATCH it.
        if let pbId = meal.pbId {
            try await patchMealAsync(pbId: pbId, from: meal, token: token)
            return
        }

        // 2) Otherwise, try POST; on 400/409 conflict, find by localId and PATCH
        do {
            let _ = try await postMealAsync(from: meal, token: token)
        } catch let e as HTTPError {
            // Log once
            print("⚠️ POST failed status=\(e.status): \(e.bodyPrefix)")
            if [400, 409, 422].contains(e.status) {
                if let existing = try await findByLocalIdAsync(meal.localId, token: token) {
                    try await patchMealAsync(pbId: existing.id, from: meal, token: token)
                } else {
                    throw e
                }
            } else {
                throw e
            }
        }

    }

    // MARK: - HTTP helpers (async)

    private struct PBRecord: Decodable { let id: String }

    private enum HTTPError: Error {
        case code(Int, String) // status, body
        var status: Int { if case .code(let s, _) = self { s } else { -1 } }
        var bodyPrefix: String {
            if case .code(_, let b) = self { return String(b.prefix(200)) }
            return ""
        }
    }


    private func postMealAsync(from meal: Meal, token: String) async throws -> PBRecord {
        guard let userId = self.userId else { throw URLError(.userAuthenticationRequired) }

        var req = URLRequest(url: URL(string: "\(baseURL)/api/collections/meals/records")!)
        req.httpMethod = "POST"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let payload: [String: Any] = [
            "localId": meal.localId,
            "text": meal.text,
            "timestamp": ISO8601DateFormatter().string(from: meal.timestamp),
            "user": userId                                 // ⬅️ include user like your old upload
        ]
        req.httpBody = try JSONSerialization.data(withJSONObject: payload)

        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
        guard (200..<300).contains(code) else {
            throw HTTPError.code(code, String(data: data, encoding: .utf8) ?? "")
        }
        print("📦 POST ok:", meal.localId)
        return try JSONDecoder().decode(PBRecord.self, from: data)
    }


    private func patchMealAsync(pbId: String, from meal: Meal, token: String) async throws {
        var req = URLRequest(url: URL(string: "\(baseURL)/api/collections/meals/records/\(pbId)")!)
        req.httpMethod = "PATCH"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let payload: [String: Any] = [
            "localId": meal.localId, // defensive: keep identity aligned
            "text": meal.text,
            "timestamp": ISO8601DateFormatter().string(from: meal.timestamp)
        ]
        req.httpBody = try JSONSerialization.data(withJSONObject: payload)

        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
        guard (200..<300).contains(code) else {
            throw HTTPError.code(code, String(data: data, encoding: .utf8) ?? "")
        }
        print("📝 PATCH ok:", meal.localId)
    }

    private func findByLocalIdAsync(_ localId: String, token: String) async throws -> PBRecord? {
        // filter=localId="..."
        let raw = "filter=localId=\"\(localId)\""
        let qs  = raw.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? raw
        let url = URL(string: "\(baseURL)/api/collections/meals/records?\(qs)&perPage=1")!

        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
        guard (200..<300).contains(code) else {
            throw HTTPError.code(code, String(data: data, encoding: .utf8) ?? "")
        }

        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let items = json["items"] as? [[String: Any]],
           let first = items.first,
           let id = first["id"] as? String {
            return PBRecord(id: id)
        }
        return nil
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
