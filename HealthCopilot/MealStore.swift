import Foundation
import UIKit
import ImageIO

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
    func updateMeal(meal: Meal, newText: String, newDate: Date, newImageData: Data?) {
        // 1) Update local fields and queue a sync (unchanged)
        if let i = meals.firstIndex(where: { $0.localId == meal.localId }) {
            meals[i].text = newText
            meals[i].timestamp = newDate
            meals[i].pendingSync = true
            meals[i].updatedAt = Date()   // ← keep LWW semantics
            saveMeals()

            // This kicks JSON PATCH for text/date
            SyncManager.shared.pushDirty()
        }

        // 2) If user picked a photo, upload/replace it on PocketBase
        if let data = newImageData {
            // (optional) compress to ~85% JPEG as you already do elsewhere
            let compressed: Data = {
                if let ui = UIImage(data: data),
                   let jpeg = ui.jpegData(compressionQuality: 0.85) { return jpeg }
                return data
            }()

            Task {
                do {
                    try await SyncManager.shared.setMealPhoto(for: meal, imageData: compressed)
                } catch {
                    print("❌ setMealPhoto error:", error.localizedDescription)
                }
            }
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
    
    func addMealWithImage(text: String, imageData originalData: Data, takenAt: Date?) {
        let pickedTimestamp: Date
        if let exifDate = photoCaptureDate(from: originalData) {
            pickedTimestamp = exifDate
        } else if let takenAt = takenAt {
            pickedTimestamp = takenAt
        } else {
            pickedTimestamp = Date()
        }



        
        var newMeal = Meal(text: text, timestamp: pickedTimestamp)
        newMeal.pendingSync = true
        newMeal.updatedAt = Date()
        meals.append(newMeal)
        saveMeals()
        
        print("➕ [LOCAL] meal added:",
              "localId=\(newMeal.localId)",
              "pbId=\(newMeal.pbId ?? "nil")",
              "timestamp=\(pickedTimestamp)",
              "text.len=\(text.count)")
        
        // Compress to ~85% JPEG for a good balance; tweak to taste
        let compressed: Data
        if let ui = UIImage(data: originalData),
           let jpeg = ui.jpegData(compressionQuality: 0.85) {
            compressed = jpeg
            print("🗜️ Compressed image:", originalData.count, "→", compressed.count, "bytes")
        } else {
            compressed = originalData
            print("⚠️ Using original image bytes:", originalData.count)
        }
        
        // Kick the multipart POST immediately (so the photo filename comes back)
        Task {
            do {
                try await SyncManager.shared.uploadMealWithImage(meal: newMeal, imageData: compressed)
            } catch {
                print("❌ uploadMealWithImage error:", error)
            }
        }
    }
    
    func photoCaptureDate(from imageData: Data) -> Date? {
        guard let src = CGImageSourceCreateWithData(imageData as CFData, nil),
              let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] else { return nil }

        if let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any],
           let s = exif[kCGImagePropertyExifDateTimeOriginal] as? String {
            let df = DateFormatter()
            df.locale = Locale(identifier: "en_US_POSIX")
            df.timeZone = .current   // 👈 interpret as local wall clock
            df.dateFormat = "yyyy:MM:dd HH:mm:ss"
            return df.date(from: s)
        }

        return nil
    }

    
    // Save/replace the PocketBase filename on a local meal
    func updatePhoto(localId: String, filename: String) {
        if let i = meals.firstIndex(where: { $0.localId == localId }) {
            meals[i].photo = filename
            saveMeals()
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

                // 🧪 DEBUG: show merge inputs
                print("""
                🔍 MERGE for localId=\(server.localId)
                   local.updatedAt=\(String(describing: local.updatedAt))
                   server.updatedAt=\(String(describing: server.updatedAt))
                   local.pbId=\(local.pbId ?? "nil"), server.pbId=\(server.pbId ?? "nil")
                   local.photo=\(local.photo ?? "nil"), server.photo=\(server.photo ?? "nil")
                """)

                // 🔒 Tombstone protection (unchanged)
                if local.isDeleted {
                    print("   🚫 local is tombstoned → keep local delete, skip server overwrite")
                    byLocal[server.localId] = local
                    continue
                }

                // "Last-writer-wins" timestamps
                let localUpdated  = age(local.updatedAt)
                let serverUpdated = age(server.updatedAt)

                if serverUpdated > localUpdated {
                    // ✅ Server wins — copy all authoritative fields
                    local.pbId        = server.pbId ?? local.pbId
                    local.text        = server.text
                    local.timestamp   = server.timestamp
                    local.updatedAt   = server.updatedAt
                    local.photo       = server.photo ?? local.photo   // ← your earlier patch
                    local.pendingSync = false
                    byLocal[server.localId] = local
                    print("   🟢 server wins; adopted fields incl. photo=\(local.photo ?? "nil")")
                } else {
                    // 🟡 Local wins — keep local edits,
                    // BUT: if local is missing a photo and server has one, adopt it anyway.
                    if (local.photo == nil || local.photo?.isEmpty == true),
                       let srvPhoto = server.photo, !srvPhoto.isEmpty {
                        local.photo = srvPhoto
                        print("   📸 local wins but missing photo → adopted server photo=\(srvPhoto)")
                    } else {
                        print("   🟡 local wins; photo stays \(local.photo ?? "nil")")
                    }
                    byLocal[server.localId] = local
                }

            } else {
                // New to device → accept server row
                var fresh = server
                if fresh.isDeleted { continue }
                fresh.pendingSync = false
                byLocal[server.localId] = fresh
                print("   🆕 accepted new server meal localId=\(server.localId), photo=\(fresh.photo ?? "nil")")
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

