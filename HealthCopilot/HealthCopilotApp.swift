import SwiftUI

@main
struct HealthCopilotApp: App {
    @StateObject private var mealStore = MealStore()
    
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
