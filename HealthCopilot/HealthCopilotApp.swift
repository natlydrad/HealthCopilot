
import SwiftUI

@main
struct HealthCopilotApp: App {
    @StateObject var healthManager = HealthManager()

    var body: some Scene {
        WindowGroup {
            DashboardView()  // Or whichever view you want to test
                .environmentObject(healthManager)
        }
    }
}
