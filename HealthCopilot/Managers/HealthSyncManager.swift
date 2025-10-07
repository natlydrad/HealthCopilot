import Foundation
import HealthKit

// Reuse the same enum your SyncStatusView expects
enum SyncState: Equatable {
    case idle
    case syncing
    case upToDate(Date)
    case error(String)
}

final class HealthSyncManager: ObservableObject {
    static let shared = HealthSyncManager()
    private let hk = HealthKitManager.shared
    private let sync = SyncManager.shared
    private let cal = Calendar.current

    @Published var stepsState: SyncState = .idle
    @Published var glucoseState: SyncState = .idle

    private let lastStepsKey = "lastStepsUploadedAt"
    private let lastGlucoseKey = "lastGlucoseUploadedAt"

    private func last(_ key: String) -> Date? { UserDefaults.standard.object(forKey: key) as? Date }
    private func set(_ key: String, _ d: Date) { UserDefaults.standard.set(d, forKey: key) }

    // MARK: - Steps
    func syncSteps() {
        stepsState = .syncing
        Task.detached {
            do {
                let now = Date()
                let start = self.last(self.lastStepsKey) ?? self.cal.date(byAdding: .day, value: -7, to: now)!
                //let start = Calendar.current.date(byAdding: .day, value: -30, to: now)!
                let raw = await withCheckedContinuation { cont in
                    self.hk.fetchStepData(start: start, end: now) { cont.resume(returning: $0) }
                }
                
                print("📊 [HealthSync] fetched \(raw.count) step samples")
                
                let bins = self.hk.binSteps(raw)
                for s in bins where s.steps > 0 {
                    await self.sync.uploadStep(timestamp: s.date, steps: s.steps)
                }
                await MainActor.run {
                    self.set(self.lastStepsKey, now)
                    self.stepsState = .upToDate(now)
                }
            } catch {
                await MainActor.run { self.stepsState = .error(error.localizedDescription) }
            }
        }
    }

    // MARK: - Glucose
    func syncGlucose() {
        glucoseState = .syncing
        Task.detached {
            do {
                let now = Date()
                let start = self.last(self.lastGlucoseKey) ?? self.cal.date(byAdding: .day, value: -7, to: now)!
                //let start = Calendar.current.date(byAdding: .day, value: -30, to: now)!
                
                print("🕒 [HealthSync] step query range:", start, "→", now, "| Δ", now.timeIntervalSince(start)/60, "minutes")

                
                let samples = await withCheckedContinuation { cont in
                    self.hk.fetchGlucoseData(start: start, end: now) { cont.resume(returning: $0) }
                }

                let unique = Dictionary(grouping: samples, by: \.date)
                    .compactMapValues { $0.first }
                    .values
                    .sorted(by: { $0.date < $1.date })
                
                print("🩸 [HealthSync] fetched \(samples.count) glucose samples")

                
                for g in samples {
                    await self.sync.uploadGlucose(timestamp: g.date, mgdl: g.value)
                }
                
                await MainActor.run {
                    self.set(self.lastGlucoseKey, now)
                    self.glucoseState = .upToDate(now)
                }
            } catch {
                await MainActor.run { self.glucoseState = .error(error.localizedDescription) }
            }
        }
    }
}
