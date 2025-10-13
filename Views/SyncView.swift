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
                            print("🕓 Running Big Sync (multi-year backfill)…")
                            await healthSync.bigSync(monthsBack: 36)
                            isBigSyncing = false
                            print("✅ Big Sync complete")
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

                // --- Sync Status ---
                SyncStatusBar()

                Spacer()
            }
            .padding()
        }
        .navigationTitle("Sync Health Data")
        .navigationBarTitleDisplayMode(.inline)
    }
}
