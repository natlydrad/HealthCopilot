// SyncStatusView.swift
import SwiftUI

struct SyncBadge: View {
    let title: String
    let state: SyncState

    var body: some View {
        HStack(spacing: 8) {
            switch state {
            case .syncing:
                ProgressView().scaleEffect(0.8)
            case .upToDate(let d):
                Image(systemName: "checkmark.seal.fill")
                Text(Self.rel(d))
            case .error:
                Image(systemName: "exclamationmark.triangle.fill")
            case .idle:
                Image(systemName: "clock")
            }
            Text(title).font(.caption).opacity(0.8)
        }
        .padding(8).background(Color.secondary.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    static func rel(_ d: Date) -> String {
        let f = RelativeDateTimeFormatter(); f.unitsStyle = .abbreviated
        return f.localizedString(for: d, relativeTo: Date())
    }
}

struct SyncStatusBar: View {
    @ObservedObject var sync = HealthSyncManager.shared
    var body: some View {
        VStack(spacing: 12) {
            Spacer()
            SyncBadge(title: "Steps", state: sync.stepsState)
            SyncBadge(title: "Glucose", state: sync.glucoseState)
            Button("Sync") {
                HealthSyncManager.shared.syncSteps()
                HealthSyncManager.shared.syncGlucose()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(.horizontal)
    }
}
