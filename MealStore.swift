import Foundation
import UIKit
import ImageIO

// MARK: - Image Compression Helpers

/// Resize image to max dimension while preserving aspect ratio
/// Ensures result is under 4.5MB to stay within PocketBase's 5MB limit
func resizeAndCompressImage(_ image: UIImage, maxDimension: CGFloat = 1024, quality: CGFloat = 0.60) -> Data? {
    // Calculate new size preserving aspect ratio
    let size = image.size
    let ratio = min(maxDimension / size.width, maxDimension / size.height)
    
    // Only resize if image is larger than max dimension
    let newSize: CGSize
    if ratio < 1 {
        newSize = CGSize(width: size.width * ratio, height: size.height * ratio)
    } else {
        newSize = size
    }
    
    // Render resized image
    let format = UIGraphicsImageRendererFormat()
    format.scale = 1.0  // Don't multiply by screen scale
    let renderer = UIGraphicsImageRenderer(size: newSize, format: format)
    let resized = renderer.image { _ in
        image.draw(in: CGRect(origin: .zero, size: newSize))
    }
    
    // Try progressively lower quality until under 4.5MB
    let maxBytes = 4_500_000
    var currentQuality = quality
    var data = resized.jpegData(compressionQuality: currentQuality)
    
    while let d = data, d.count > maxBytes && currentQuality > 0.1 {
        currentQuality -= 0.1
        data = resized.jpegData(compressionQuality: currentQuality)
        print("🗜️ Recompressing at quality \(currentQuality): \(d.count) → \(data?.count ?? 0) bytes")
    }
    
    return data
}

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
            // Resize to 1024px max + compress to 65% quality (~60-120KB)
            let compressed: Data = {
                if let ui = UIImage(data: data),
                   let optimized = resizeAndCompressImage(ui) { return optimized }
                return data
            }()
            print("🗜️ [updateMeal] Compressed image:", data.count, "→", compressed.count, "bytes")

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
    func markSynced(localId: String, save: Bool = true) {
        if let idx = meals.firstIndex(where: { $0.localId == localId }) {
            meals[idx].pendingSync = false
            meals[idx].updatedAt = Date()
            if save { saveMeals() }
        }
    }

    
    // Link PB id into the existing local meal (called after POST succeeds)
    func linkLocalToRemote(localId: String, pbId: String, save: Bool = true) {
        if let i = meals.firstIndex(where: { $0.localId == localId }) {
            meals[i].pbId = pbId
            if save { saveMeals() }
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
        // Determine timestamp (prefer EXIF)
        let pickedTimestamp: Date
        if let exifDate = photoCaptureDate(from: originalData) {
            pickedTimestamp = exifDate
        } else if let takenAt = takenAt {
            pickedTimestamp = takenAt
        } else {
            pickedTimestamp = Date()
        }

        // Create a new local meal record
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

        // Resize to 1024px max + compress to 65% quality (~60-120KB)
        let compressed: Data
        if let ui = UIImage(data: originalData),
           let optimized = resizeAndCompressImage(ui) {
            compressed = optimized
            print("🗜️ Compressed image:", originalData.count, "→", compressed.count, "bytes (\(Int(Double(compressed.count) / Double(originalData.count) * 100))%)")
        } else {
            compressed = originalData
            print("⚠️ Using original image bytes:", originalData.count)
        }

        // --- 🆕 Save image locally so it shows up offline + can retry later ---
        let imgName = "meal-\(newMeal.localId).jpg"
        let imgURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)
            .first!.appendingPathComponent(imgName)
        do {
            try compressed.write(to: imgURL)
            newMeal.photo = imgName
            if let i = meals.firstIndex(where: { $0.localId == newMeal.localId }) {
                meals[i] = newMeal
            }
            saveMeals()
            objectWillChange.send()
            print("💾 Saved local image:", imgURL.lastPathComponent)

        } catch {
            print("⚠️ Failed to save local image:", error)
        }

        // --- Try immediate upload (will fail gracefully offline) ---
        Task {
            do {
                try await SyncManager.shared.uploadMealWithImage(meal: newMeal, imageData: compressed)
                // Keep local file as backup - cleanup happens separately
                print("✅ Upload succeeded, keeping local backup: \(imgName)")
            } catch {
                print("❌ uploadMealWithImage error:", error.localizedDescription)
                // Leave local file; SyncManager.pushDirty() will retry later
            }
        }
    }
    
    // MARK: - Local Image Cleanup (2 week retention)
    
    /// Delete local meal images older than the retention period
    /// Call this periodically (e.g., on app launch or daily)
    func cleanupOldLocalImages(retentionDays: Int = 14) {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let cutoffDate = Calendar.current.date(byAdding: .day, value: -retentionDays, to: Date())!
        
        var deletedCount = 0
        var keptCount = 0
        
        for meal in meals {
            guard let photoName = meal.photo,
                  photoName.hasPrefix("meal-"),  // Only delete local files, not PB filenames
                  meal.pbId != nil else {        // Only if successfully synced to server
                continue
            }
            
            // Check if meal is older than retention period
            if meal.timestamp < cutoffDate {
                let imgURL = docs.appendingPathComponent(photoName)
                if FileManager.default.fileExists(atPath: imgURL.path) {
                    do {
                        try FileManager.default.removeItem(at: imgURL)
                        deletedCount += 1
                        print("🗑️ Cleaned up old image: \(photoName)")
                    } catch {
                        print("⚠️ Failed to delete \(photoName): \(error)")
                    }
                }
            } else {
                keptCount += 1
            }
        }
        
        if deletedCount > 0 || keptCount > 0 {
            print("🧹 Image cleanup: deleted \(deletedCount), kept \(keptCount) (within \(retentionDays) days)")
        }
    }
    
    /// Get local image data if available (for re-upload after server loss)
    func getLocalImageData(for meal: Meal) -> Data? {
        guard let photoName = meal.photo, photoName.hasPrefix("meal-") else {
            return nil
        }
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let imgURL = docs.appendingPathComponent(photoName)
        return try? Data(contentsOf: imgURL)
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
    
    private var lastSaveLog: Date = .distantPast
    
    func saveMeals() {
        let url = getFileURL()
        do {
            let data = try JSONEncoder().encode(meals)
            try data.write(to: url)
            // Only log saves once per 5 seconds to reduce spam
            if Date().timeIntervalSince(lastSaveLog) > 5 {
                print("💾 Saved \(meals.count) meals")
                lastSaveLog = Date()
            }
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
    
    private func localImageURL(for localId: String) -> URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        return docs.appendingPathComponent("meal-\(localId).jpg")
    }


    func mergeFetched(_ remote: [Meal]) {
        print("🔗 mergeFetched: remote=\(remote.count) local(before)=\(meals.count)")

        // Fast lookup by localId for local records
        var byLocal = Dictionary(uniqueKeysWithValues: meals.map { ($0.localId, $0) })

        for server in remote {
            if var local = byLocal[server.localId] {

                // 🧪 DEBUG: show merge inputs
                /*
                print("""
                🔍 MERGE for localId=\(server.localId)
                   local.updatedAt=\(String(describing: local.updatedAt))
                   server.updatedAt=\(String(describing: server.updatedAt))
                   local.pbId=\(local.pbId ?? "nil"), server.pbId=\(server.pbId ?? "nil")
                   local.photo=\(local.photo ?? "nil"), server.photo=\(server.photo ?? "nil")
                """)
                */

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
                        //print("   🟡 local wins; photo stays \(local.photo ?? "nil")")
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

