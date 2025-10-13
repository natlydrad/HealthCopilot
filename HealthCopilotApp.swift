import SwiftUI

@main
struct HealthCopilotApp: App {
    // ⬇️ Use the same instance that SyncManager updates
    @StateObject private var mealStore = MealStore.shared
    @Environment(\.scenePhase) private var scenePhase



    init() {
        // Login to PocketBase on startup
        SyncManager.shared.login(email: "natradalie@gmail.com",
                                 password: "London303!") { success in
            if success {
                print("✅ Logged in to PocketBase; initial fetch")
                
                let key = "didRunReconcileV1"
                if !UserDefaults.standard.bool(forKey: key) {
                    SyncManager.shared.reconcileLocalWithServer()
                    UserDefaults.standard.set(true, forKey: key)
                }
                
                SyncManager.shared.pushDirty()
                SyncManager.shared.fetchMeals()   // pull from PB on launch
            } else {
                print("❌ Login failed")
            }
        }
    }

    var body: some Scene {
        WindowGroup {
            TabView {
                NavigationView { LogView(store: mealStore).navigationBarTitleDisplayMode(.inline) }
                    .tabItem { Label("Log Meal", systemImage: "plus.circle") }

                NavigationView { VerifyView(store: mealStore) }
                    .tabItem { Label("Verify", systemImage: "checkmark.circle") }
            }
            
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
