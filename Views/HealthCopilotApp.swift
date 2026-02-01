import SwiftUI

@main
struct HealthCopilotApp: App {
    // ⬇️ Use the same instance that SyncManager updates
    @StateObject private var mealStore = MealStore.shared
    @Environment(\.scenePhase) private var scenePhase



    init() {
        print("🚀🚀🚀 APP INIT STARTED 🚀🚀🚀")
        // Login to PocketBase on startup
        SyncManager.shared.login(email: "natradalie@gmail.com",
                                 password: "London303!") { success in
            if success {
                print("✅ Logged in to PocketBase; initial fetch")
                
                // Always reconcile on launch to catch stuck/orphaned meals
                SyncManager.shared.reconcileLocalWithServer()
                
                SyncManager.shared.fetchMeals()   // pull from PB on launch
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
