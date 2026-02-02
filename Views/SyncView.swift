// SyncView.swift
import SwiftUI

struct SyncView: View {
    @ObservedObject var healthSync = HealthSyncManager.shared
    @State private var isBigSyncing = false
    @State private var isResyncingMeals = false
    @State private var resyncStatus = ""

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // --- Header Buttons ---
                HStack(spacing: 12) {
                    Button {
                        Task {
                            print("🔄 Manual Sync Recent pressed")
                            await healthSync.syncRecentDay()
                        }
                    } label: {
                        Label("Sync Recent", systemImage: "arrow.clockwise.circle")
                    }
                    .buttonStyle(.bordered)

                    Button {
                        Task {
                            guard !isBigSyncing else { return }
                            isBigSyncing = true
                            await healthSync.bigSync(monthsBack: 9)
                            isBigSyncing = false
                        }
                    } label: {
                        if isBigSyncing {
                            ProgressView()
                        } else {
                            Label("Big Sync", systemImage: "clock.arrow.circlepath")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isBigSyncing)
                }
                .padding(.top, 12)
                
                // --- Force Resync Meals Button ---
                VStack(spacing: 8) {
                    Button {
                        guard !isResyncingMeals else { return }
                        isResyncingMeals = true
                        resyncStatus = "Checking for orphaned meals..."
                        
                        // Run reconcile which detects orphaned meals
                        SyncManager.shared.reconcileLocalWithServer()
                        
                        // Give it a moment then update status
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            let pending = MealStore.shared.meals.filter { $0.pendingSync }.count
                            if pending > 0 {
                                resyncStatus = "Found \(pending) meals to sync. Uploading..."
                                SyncManager.shared.pushDirty()
                                DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                                    resyncStatus = "Done! Check server for meals."
                                    isResyncingMeals = false
                                }
                            } else {
                                resyncStatus = "All meals are synced!"
                                isResyncingMeals = false
                            }
                        }
                    } label: {
                        if isResyncingMeals {
                            ProgressView()
                        } else {
                            Label("Force Resync Meals", systemImage: "arrow.triangle.2.circlepath")
                        }
                    }
                    .buttonStyle(.bordered)
                    .tint(.orange)
                    .disabled(isResyncingMeals)
                    
                    if !resyncStatus.isEmpty {
                        Text(resyncStatus)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    
                    Text("Use if meals are missing from server")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }

                Divider().padding(.vertical, 8)

                // --- Sync summary (reads from shared HealthSyncManager) ---
                if let lastSync = healthSync.lastSyncTime {
                    VStack(spacing: 4) {
                        Text("Last Sync:\n\(formatTime(lastSync))")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                        Text("Range: \(healthSync.lastSyncRange)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding(.bottom, 4)
                    .transition(.opacity)

                } else {
                    Text("No sync data yet")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                // --- Sync Status ---
                SyncStatusBar()

                Spacer()
            }
            .padding()
        }
        .navigationTitle("Sync Health Data")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            print("🟢 SyncView appeared | lastSyncTime:",
                  healthSync.lastSyncTime as Any,
                  "| range:", healthSync.lastSyncRange)
        }
    }

    private func formatTime(_ date: Date) -> String {
        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "h:mma"   // e.g. "1:14PM"
        timeFormatter.amSymbol = "am"
        timeFormatter.pmSymbol = "pm"

        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "MMM d, yyyy" // e.g. "Oct 15, 2025"

        let relativeFormatter = RelativeDateTimeFormatter()
        relativeFormatter.unitsStyle = .full     // "2 days ago"

        let timeString = timeFormatter.string(from: date)
        let relativeString = relativeFormatter.localizedString(for: date, relativeTo: Date())
        let dateString = dateFormatter.string(from: date)

        return "\(timeString), \(relativeString), \(dateString)"
    }


}
