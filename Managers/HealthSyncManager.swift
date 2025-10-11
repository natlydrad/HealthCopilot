// HealthSyncManager.swift
import Foundation

enum SyncState: Equatable {
    case idle
    case syncing
    case upToDate(Date)
    case error(String)
}

@MainActor
final class HealthSyncManager: ObservableObject {
    static let shared = HealthSyncManager()

    private let hk = HealthKitManager.shared
    private let sync = SyncManager.shared
    private let cal = Calendar.current

    @Published var stepsState: SyncState = .idle
    @Published var glucoseState: SyncState = .idle
    @Published var sleepState: SyncState = .idle
    @Published var energyState: SyncState = .idle
    @Published var heartState: SyncState = .idle
    @Published var bodyState: SyncState = .idle

    private let lastStepsKey   = "lastStepsUploadedAt"
    private let lastGlucoseKey = "lastGlucoseUploadedAt"
    private let lastSleepKey   = "lastSleepUploadedAt"
    private let lastEnergyKey  = "lastEnergyUploadedAt"
    private let lastHeartKey   = "lastHeartUploadedAt"
    private let lastBodyKey    = "lastBodyUploadedAt"

    private func last(_ key: String) -> Date? { UserDefaults.standard.object(forKey: key) as? Date }
    private func set(_ key: String, _ d: Date) { UserDefaults.standard.set(d, forKey: key) }

    // MARK: - Public entrypoint to sync "last N months"
    func syncAll(monthsBack: Int = 6) {
        syncSteps()
        syncGlucose()
        syncSleep(monthsBack: monthsBack)
        syncEnergy(monthsBack: monthsBack)
        syncHeart(monthsBack: monthsBack)
        syncBody(monthsBack: monthsBack)
    }

    // MARK: - Steps

    func syncSteps() {
        stepsState = .syncing
        Task.detached {
            do {
                let now = Date()
                // 🗓 Backfill 6 months instead of 30 days
                let start = Calendar.current.date(byAdding: .day, value: -180, to: now)!
                print("📆 [syncSteps] syncing from \(start) → \(now)")

                // Fetch from HealthKit
                let raw = await withCheckedContinuation { cont in
                    self.hk.fetchStepData(start: start, end: now, intervalMinutes: 5) {
                        cont.resume(returning: $0)
                    }
                }

                // ✅ Preload all existing timestamps from PocketBase
                let existing = await self.sync.fetchExistingStepDates()
                let existingSet = Set(existing.map { Calendar.current.startOfMinute(for: $0) })
                var uploaded = Set<Date>()

                // Upload only new 5-min bins
                for s in raw.sorted(by: { $0.date < $1.date }) where s.steps > 0 {
                    let minute = Calendar.current.startOfMinute(for: s.date)
                    guard !uploaded.contains(minute),
                          !existingSet.contains(minute)
                    else { continue }

                    uploaded.insert(minute)
                    await self.sync.uploadStep(timestamp: s.date, steps: s.steps)
                }

                await MainActor.run {
                    if !uploaded.isEmpty {
                        self.set(self.lastStepsKey, uploaded.sorted().last ?? now)
                    }
                    self.stepsState = .upToDate(now)
                }

                print("✅ [syncSteps] uploaded \(uploaded.count) new records")
            } catch {
                await MainActor.run {
                    self.stepsState = .error(error.localizedDescription)
                }
                print("❌ [syncSteps] error:", error.localizedDescription)
            }
        }
    }



    // MARK: - Glucose

    func syncGlucose() {
        glucoseState = .syncing
        Task.detached {
            await self.runGlucoseSync()
        }

    }
    
    private func runGlucoseSync() async {
        do {
            let now = Date()
            let start = self.cal.date(byAdding: .day, value: -180, to: now)!
            let samples = await withCheckedContinuation { cont in
                self.hk.fetchGlucoseData(start: start, end: now) { cont.resume(returning: $0) }
            }

            // dedupe across PocketBase
            let existing = await self.sync.fetchExistingGlucoseDates()
            let existingSet = Set(existing.map { Calendar.current.startOfMinute(for: $0) })
            var uploaded = Set<Date>()

            for g in samples.sorted(by: { $0.date < $1.date }) {
                let minute = Calendar.current.startOfMinute(for: g.date)
                guard !uploaded.contains(minute),
                      !existingSet.contains(minute)
                else { continue }

                uploaded.insert(minute)
                await self.sync.uploadGlucose(timestamp: g.date, mgdl: g.value)
            }

            await MainActor.run {
                self.set(self.lastGlucoseKey, now)
                self.glucoseState = .upToDate(now)
            }
        } catch {
            await MainActor.run {
                self.glucoseState = .error(error.localizedDescription)
            }
        }
    }


    // MARK: - Sleep → daily totals per wake-date

    func syncSleep(monthsBack: Int = 6) {
        sleepState = .syncing
        Task.detached {
            do {
                let now = Date()
                let start = self.cal.date(byAdding: .month, value: -monthsBack, to: now)!
                let episodes = await withCheckedContinuation { cont in
                    self.hk.fetchSleepEpisodes(start: start, end: now) { cont.resume(returning: $0) }
                }

                // Aggregate by wake-date (assign an episode to the day it ends)
                struct Totals { var inBed=0.0, core=0.0, deep=0.0, rem=0.0, asleep=0.0 }
                var byDay: [Date: Totals] = [:]

                for e in episodes {
                    let dur = e.end.timeIntervalSince(e.start) / 60.0 // minutes
                    let wakeDay = self.cal.startOfDay(for: e.end)
                    var t = byDay[wakeDay, default: Totals()]
                    switch e.stage {
                    case "inBed":      t.inBed += dur
                    case "asleepCore": t.core  += dur; t.asleep += dur
                    case "asleepDeep": t.deep  += dur; t.asleep += dur
                    case "asleepREM":  t.rem   += dur; t.asleep += dur
                    default:           t.asleep += dur
                    }
                    byDay[wakeDay] = t
                }

                for (day, t) in byDay.sorted(by: { $0.key < $1.key }) {
                    await self.sync.uploadSleepDaily(
                        date: day,
                        totalMin: t.asleep,
                        remMin: t.rem,
                        deepMin: t.deep,
                        coreMin: t.core,
                        inBedMin: t.inBed
                    )
                }

                await MainActor.run {
                    self.set(self.lastSleepKey, now)
                    self.sleepState = .upToDate(now)
                }
            } catch {
                await MainActor.run { self.sleepState = .error(error.localizedDescription) }
            }
        }
    }

    // MARK: - Energy → daily sums

    func syncEnergy(monthsBack: Int = 6) {
        energyState = .syncing
        Task.detached {
            do {
                let now = Date()
                let start = self.cal.date(byAdding: .month, value: -monthsBack, to: now)!

                async let active: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchActiveEnergyDaily(start: start, end: now) { cont.resume(returning: $0) }
                }
                async let basal:  [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchBasalEnergyDaily(start: start, end: now)  { cont.resume(returning: $0) }
                }

                let (a, b) = await (active, basal)
                let allDays = Set(a.map{$0.date}).union(b.map{$0.date})
                for day in allDays.sorted() {
                    let activeKcal = a.first(where: {$0.date==day})?.value ?? 0
                    let basalKcal  = b.first(where: {$0.date==day})?.value ?? 0
                    await self.sync.uploadEnergyDaily(date: day, activeKcal: activeKcal, basalKcal: basalKcal)
                }

                await MainActor.run {
                    self.set(self.lastEnergyKey, now)
                    self.energyState = .upToDate(now)
                }
            } catch {
                await MainActor.run { self.energyState = .error(error.localizedDescription) }
            }
        }
    }

    // MARK: - Heart → daily averages

    func syncHeart(monthsBack: Int = 6) {
        heartState = .syncing
        Task.detached {
            do {
                let now = Date()
                let start = self.cal.date(byAdding: .month, value: -monthsBack, to: now)!

                async let rhr: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchRestingHRDaily(start: start, end: now) { cont.resume(returning: $0) }
                }
                async let hrv: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchHRVDaily(start: start, end: now) { cont.resume(returning: $0) }
                }
                async let vo2: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchVO2MaxDaily(start: start, end: now) { cont.resume(returning: $0) }
                }

                let (r, h, v) = await (rhr, hrv, vo2)
                let allDays = Set(r.map{$0.date}).union(h.map{$0.date}).union(v.map{$0.date})
                for day in allDays.sorted() {
                    let rhrBpm = r.first(where: {$0.date==day})?.value
                    let hrvMs  = h.first(where: {$0.date==day})?.value
                    let vo2mx  = v.first(where: {$0.date==day})?.value
                    await self.sync.uploadHeartDaily(date: day,
                                                     restingHR: rhrBpm,
                                                     hrvSDNNms: hrvMs,
                                                     vo2max: vo2mx)
                }

                await MainActor.run {
                    self.set(self.lastHeartKey, now)
                    self.heartState = .upToDate(now)
                }
            } catch {
                await MainActor.run { self.heartState = .error(error.localizedDescription) }
            }
        }
    }

    // MARK: - Body → daily averages

    func syncBody(monthsBack: Int = 6) {
        bodyState = .syncing
        Task.detached {
            do {
                let now = Date()
                let start = self.cal.date(byAdding: .month, value: -monthsBack, to: now)!

                async let w: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchWeightDaily(start: start, end: now) { cont.resume(returning: $0) }
                }
                async let f: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchBodyFatDaily(start: start, end: now) { cont.resume(returning: $0) }
                }

                let (weights, fats) = await (w, f)
                let allDays = Set(weights.map{$0.date}).union(fats.map{$0.date})
                for day in allDays.sorted() {
                    let kg  = weights.first(where: {$0.date==day})?.value
                    let pct = fats.first(where: {$0.date==day})?.value
                    await self.sync.uploadBodyDaily(date: day, weightKg: kg, bodyFatPct: pct)
                }

                await MainActor.run {
                    self.set(self.lastBodyKey, now)
                    self.bodyState = .upToDate(now)
                }
            } catch {
                await MainActor.run { self.bodyState = .error(error.localizedDescription) }
            }
        }
    }
}

extension Calendar {
    func startOfMinute(for date: Date) -> Date {
        return self.date(from: self.dateComponents([.year, .month, .day, .hour, .minute], from: date))!
    }
}
