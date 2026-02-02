import SwiftUI

@main
struct HealthCopilotApp: App {
    // ⬇️ Use the same instance that SyncManager updates
    @StateObject private var mealStore = MealStore.shared
    @Environment(\.scenePhase) private var scenePhase



    init() {
        print("🚀 APP INIT")
        
        // Cleanup old local images (keep 2 weeks as backup)
        MealStore.shared.cleanupOldLocalImages(retentionDays: 14)
        
        // Login to PocketBase on startup
        SyncManager.shared.login(email: "natradalie@gmail.com",
                                 password: "London303!") { success in
            if success {
                print("✅ Logged in to PocketBase")
                
                // Light sync on startup - just fetch and merge
                let pendingCount = MealStore.shared.meals.filter { $0.pendingSync }.count
                if pendingCount > 0 {
                    print("🔄 Found \(pendingCount) unsynced meals, pushing...")
                    SyncManager.shared.pushDirty()
                }
                SyncManager.shared.fetchMeals()
            } else {
                print("❌ Login failed")
            }
        }
    }

    var body: some Scene {
        WindowGroup {
            RootView(store: mealStore)
                .onAppear {
                    HealthKitManager.shared.requestPermissions { granted in
                        print("🔐 HealthKit permission granted:", granted)
                    }
                    HealthKitManager.shared.debugListAllTypes()
                }
                .onChange(of: scenePhase) { phase in
                    print("🟦 scenePhase:", phase)
                    if phase == .active {
                        print("🟩 Foreground → fetchMeals()")
                        SyncManager.shared.pushDirty()
                        SyncManager.shared.fetchMeals()
                    }
                }
        }
    }

}
