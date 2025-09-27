import SwiftUI

@main
struct HealthCopilotApp: App {
    @StateObject private var mealStore = MealStore()
    
    init() {
        // Login to PocketBase on startup
        SyncManager.shared.login(email: "natradalie@gmail.com", password: "London303!") { success in
            if success {
                print("✅ Logged in to PocketBase")
                // Later: fetch meals from PocketBase here
            } else {
                print("❌ Login failed")
            }
        }
    }
    
    var body: some Scene {
        WindowGroup {
            TabView {
                NavigationView {
                    LogView(store: mealStore)
                }
                .tabItem {
                    Label("Log Meal", systemImage: "plus.circle")
                }

                NavigationView {
                    VerifyView(store: mealStore)
                }
                .tabItem {
                    Label("Verify", systemImage: "checkmark.circle")
                }
            }
        }
    }
}
