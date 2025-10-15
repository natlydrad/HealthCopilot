// SyncView.swift
import SwiftUI

struct SyncView: View {
    @ObservedObject var healthSync = HealthSyncManager.shared
    @State private var isBigSyncing = false

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
