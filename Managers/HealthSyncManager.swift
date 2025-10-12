//
//  HealthSyncManager.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 9/27/25.
//

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

    // UI states
    @Published var stepsState: SyncState = .idle
    @Published var glucoseState: SyncState = .idle
    @Published var sleepState: SyncState = .idle
    @Published var energyState: SyncState = .idle
    @Published var heartState: SyncState = .idle
    @Published var bodyState: SyncState = .idle

    // UserDefaults keys
    private let lastStepsKey   = "lastStepsUploadedAt"
    private let lastGlucoseKey = "lastGlucoseUploadedAt"
    private let lastSleepKey   = "lastSleepUploadedAt"
    private let lastEnergyKey  = "lastEnergyUploadedAt"
    private let lastHeartKey   = "lastHeartUploadedAt"
    private let lastBodyKey    = "lastBodyUploadedAt"

    private func last(_ key: String) -> Date? { UserDefaults.standard.object(forKey: key) as? Date }
    private func set(_ key: String, _ d: Date) { UserDefaults.standard.set(d, forKey: key) }

    // MARK: - Sync Throttling + Overlap Config
    private let throttleKeyAuto = "lastAutoSyncRecentAt"
    private let throttleMinutes = 30
    private let minuteOverlap: TimeInterval = 60 * 60 * 24       // 24h overlap for minute-level data
    private let dayOverlap: TimeInterval = 60 * 60 * 24 * 3      // 3d overlap for daily data

    private func shouldThrottle(_ key: String, minutes: Int) -> Bool {
        guard let last = UserDefaults.standard.object(forKey: key) as? Date else { return false }
        return Date().timeIntervalSince(last) < Double(minutes * 60)
    }

    private func setNow(_ key: String) {
        UserDefaults.standard.set(Date(), forKey: key)
    }

    // MARK: - Entrypoints
    func syncAll(monthsBack: Int = 6) {
        syncSteps()
        syncGlucose()
        syncSleep(monthsBack: monthsBack)
        syncEnergy(monthsBack: monthsBack)
        syncHeart(monthsBack: monthsBack)
        syncBody(monthsBack: monthsBack)
    }

    /// Fast, safe sync for recent data; throttled every 30 min
    func autoSyncRecent() {
        if shouldThrottle(throttleKeyAuto, minutes: throttleMinutes) { return }
        setNow(throttleKeyAuto)

        let now = Date()
        let stepsStart   = last(lastStepsKey)?.addingTimeInterval(-minuteOverlap) ?? now.addingTimeInterval(-3*24*60*60)
        let glucoseStart = last(lastGlucoseKey)?.addingTimeInterval(-minuteOverlap) ?? now.addingTimeInterval(-3*24*60*60)
        let dayRecentStart = last(lastSleepKey)?.addingTimeInterval(-dayOverlap)
            ?? now.addingTimeInterval(-14*24*60*60)

        syncSteps(start: stepsStart, end: now)
        syncGlucose(start: glucoseStart, end: now)
        syncSleep(start: cal.startOfDay(for: dayRecentStart), end: cal.startOfDay(for: now))
        syncEnergy(start: cal.startOfDay(for: dayRecentStart), end: cal.startOfDay(for: now))
        syncHeart(start: cal.startOfDay(for: dayRecentStart), end: cal.startOfDay(for: now))
        syncBody(start: cal.startOfDay(for: dayRecentStart), end: cal.startOfDay(for: now))
    }

    /// Deep historical sync (safe to re-run; deduped)
    func bigSync(monthsBack: Int = 60) {
        let now = Date()
        let start = cal.date(byAdding: .month, value: -monthsBack, to: now)!

        let stepsStart   = min(last(lastStepsKey)?.addingTimeInterval(-minuteOverlap) ?? now, start)
        let glucoseStart = min(last(lastGlucoseKey)?.addingTimeInterval(-minuteOverlap) ?? now, start)
        let dayStart = cal.startOfDay(for:
            min(
                last(lastSleepKey)?.addingTimeInterval(-dayOverlap)
                ?? last(lastEnergyKey)?.addingTimeInterval(-dayOverlap)
                ?? last(lastHeartKey)?.addingTimeInterval(-dayOverlap)
                ?? last(lastBodyKey)?.addingTimeInterval(-dayOverlap)
                ?? now,
                start
            )
        )

        syncSteps(start: stepsStart, end: now)
        syncGlucose(start: glucoseStart, end: now)
        syncSleep(start: dayStart, end: cal.startOfDay(for: now))
        syncEnergy(start: dayStart, end: cal.startOfDay(for: now))
        syncHeart(start: dayStart, end: cal.startOfDay(for: now))
        syncBody(start: dayStart, end: cal.startOfDay(for: now))
    }

    // MARK: - Steps
    func syncSteps() {
        let now = Date()
        let start = Calendar.current.date(byAdding: .day, value: -180, to: now)!
        syncSteps(start: start, end: now)
    }

    func syncSteps(start: Date, end: Date) {
        stepsState = .syncing
        Task.detached {
            do {
                print("📆 [syncSteps] \(start) → \(end)")

                let raw = await withCheckedContinuation { cont in
                    self.hk.fetchStepData(start: start, end: end, intervalMinutes: 5) {
                        cont.resume(returning: $0)
                    }
                }

                let existing = await self.sync.fetchExistingStepDates()
                let existingSet = Set(existing.map { Calendar.current.startOfMinute(for: $0) })
                var uploaded = Set<Date>()

                for s in raw.sorted(by: { $0.date < $1.date }) where s.steps > 0 {
                    let minute = Calendar.current.startOfMinute(for: s.date)
                    guard !uploaded.contains(minute), !existingSet.contains(minute) else { continue }
                    uploaded.insert(minute)
                    await self.sync.uploadStep(timestamp: minute, steps: s.steps)
                }

                await MainActor.run {
                    if let lastUploaded = uploaded.sorted().last {
                        self.set(self.lastStepsKey, lastUploaded)
                    } else {
                        self.set(self.lastStepsKey, end)
                    }
                    self.stepsState = .upToDate(Date())
                }

                print("✅ [syncSteps] uploaded \(uploaded.count) new records")
            } catch {
                await MainActor.run { self.stepsState = .error(error.localizedDescription) }
            }
        }
    }

    // MARK: - Glucose
    func syncGlucose() {
        let now = Date()
        let start = self.cal.date(byAdding: .day, value: -180, to: now)!
        syncGlucose(start: start, end: now)
    }

    func syncGlucose(start: Date, end: Date) {
        glucoseState = .syncing
        Task.detached { await self.runGlucoseSync(start: start, end: end) }
    }

    private func runGlucoseSync(start: Date, end: Date) async {
        do {
            let samples = await withCheckedContinuation { cont in
                self.hk.fetchGlucoseData(start: start, end: end) { cont.resume(returning: $0) }
            }

            let existing = await self.sync.fetchExistingGlucoseDates()
            let existingSet = Set(existing.map { Calendar.current.startOfMinute(for: $0) })
            var uploaded = Set<Date>()

            for g in samples.sorted(by: { $0.date < $1.date }) {
                let minute = Calendar.current.startOfMinute(for: g.date)
                guard !uploaded.contains(minute), !existingSet.contains(minute) else { continue }
                uploaded.insert(minute)
                await self.sync.uploadGlucose(timestamp: minute, mgdl: g.value)
            }

            await MainActor.run {
                self.set(self.lastGlucoseKey, end)
                self.glucoseState = .upToDate(Date())
            }
        } catch {
            await MainActor.run { self.glucoseState = .error(error.localizedDescription) }
        }
    }

    // MARK: - Sleep
    func syncSleep(monthsBack: Int = 6) {
        let now = Date()
        let start = self.cal.date(byAdding: .month, value: -monthsBack, to: now)!
        syncSleep(start: start, end: now)
    }

    func syncSleep(start: Date, end: Date) {
        sleepState = .syncing
        Task.detached {
            do {
                let episodes = await withCheckedContinuation { cont in
                    self.hk.fetchSleepEpisodes(start: start, end: end) { cont.resume(returning: $0) }
                }

                struct Totals { var inBed=0.0, core=0.0, deep=0.0, rem=0.0, asleep=0.0 }
                var byDay: [Date: Totals] = [:]

                for e in episodes {
                    let dur = e.end.timeIntervalSince(e.start) / 60.0
                    let wakeDay = self.cal.startOfDay(for: e.end)
                    var t = byDay[wakeDay, default: Totals()]
                    switch e.stage {
                    case "inBed": t.inBed += dur
                    case "asleepCore": t.core += dur; t.asleep += dur
                    case "asleepDeep": t.deep += dur; t.asleep += dur
                    case "asleepREM": t.rem += dur;  t.asleep += dur
                    default: t.asleep += dur
                    }
                    byDay[wakeDay] = t
                }

                let existingDays = await self.sync.fetchExistingSleepDays()
                let existingSet = Set(existingDays.map { self.cal.startOfDay(for: $0) })

                for (day, t) in byDay.sorted(by: { $0.key < $1.key }) {
                    guard !existingSet.contains(day) else { continue }
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
                    self.set(self.lastSleepKey, end)
                    self.sleepState = .upToDate(Date())
                }
            } catch {
                await MainActor.run { self.sleepState = .error(error.localizedDescription) }
            }
        }
    }

    // MARK: - Energy
    func syncEnergy(monthsBack: Int = 6) {
        let now = Date()
        let start = self.cal.date(byAdding: .month, value: -monthsBack, to: now)!
        syncEnergy(start: start, end: now)
    }

    func syncEnergy(start: Date, end: Date) {
        energyState = .syncing
        Task.detached {
            do {
                async let active: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchActiveEnergyDaily(start: start, end: end) { cont.resume(returning: $0) }
                }
                async let basal: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchBasalEnergyDaily(start: start, end: end) { cont.resume(returning: $0) }
                }

                let (a, b) = await (active, basal)
                let allDays = Set(a.map{$0.date}).union(b.map{$0.date})
                for day in allDays.sorted() {
                    let activeKcal = a.first(where: {$0.date==day})?.value ?? 0
                    let basalKcal  = b.first(where: {$0.date==day})?.value ?? 0
                    await self.sync.uploadEnergyDaily(date: day, activeKcal: activeKcal, basalKcal: basalKcal)
                }

                await MainActor.run {
                    self.set(self.lastEnergyKey, end)
                    self.energyState = .upToDate(Date())
                }
            } catch {
                await MainActor.run { self.energyState = .error(error.localizedDescription) }
            }
        }
    }

    // MARK: - Heart
    func syncHeart(monthsBack: Int = 6) {
        let now = Date()
        let start = self.cal.date(byAdding: .month, value: -monthsBack, to: now)!
        syncHeart(start: start, end: now)
    }

    func syncHeart(start: Date, end: Date) {
        heartState = .syncing
        Task.detached {
            do {
                async let rhr: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchRestingHRDaily(start: start, end: end) { cont.resume(returning: $0) }
                }
                async let hrv: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchHRVDaily(start: start, end: end) { cont.resume(returning: $0) }
                }
                async let vo2: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchVO2MaxDaily(start: start, end: end) { cont.resume(returning: $0) }
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
                    self.set(self.lastHeartKey, end)
                    self.heartState = .upToDate(Date())
                }
            } catch {
                await MainActor.run { self.heartState = .error(error.localizedDescription) }
            }
        }
    }

    // MARK: - Body
    func syncBody(monthsBack: Int = 6) {
        let now = Date()
        let start = self.cal.date(byAdding: .month, value: -monthsBack, to: now)!
        syncBody(start: start, end: now)
    }

    func syncBody(start: Date, end: Date) {
        bodyState = .syncing
        Task.detached {
            do {
                async let w: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchWeightDaily(start: start, end: end) { cont.resume(returning: $0) }
                }
                async let f: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                    self.hk.fetchBodyFatDaily(start: start, end: end) { cont.resume(returning: $0) }
                }

                let (weights, fats) = await (w, f)
                let allDays = Set(weights.map{$0.date}).union(fats.map{$0.date})
                for day in allDays.sorted() {
                    let kg  = weights.first(where: {$0.date==day})?.value
                    let pct = fats.first(where: {$0.date==day})?.value
                    await self.sync.uploadBodyDaily(date: day, weightKg: kg, bodyFatPct: pct)
                }

                await MainActor.run {
                    self.set(self.lastBodyKey, end)
                    self.bodyState = .upToDate(Date())
                }
            } catch {
                await MainActor.run { self.bodyState = .error(error.localizedDescription) }
            }
        }
    }
    
    func syncRecentDay() async {
            print("⚡️ Running 24h auto-sync for all major metrics…")
            await withTaskGroup(of: Void.self) { group in
                group.addTask { await self.syncStepsRecent(daysBack: 1) }
                group.addTask { await self.syncGlucoseRecent(daysBack: 1) }
                group.addTask { await self.syncSleep(monthsBack: 0) }     // 1 day ≈ 0 months
                group.addTask { await self.syncEnergy(monthsBack: 0) }
                group.addTask { await self.syncHeart(monthsBack: 0) }
                group.addTask { await self.syncBody(monthsBack: 0) }
            }
        }

        // same code as your full ones, just with a `daysBack` param
        func syncStepsRecent(daysBack: Int) async {
            stepsState = .syncing
            let now = Date()
            let start = Calendar.current.date(byAdding: .day, value: -daysBack, to: now)!
            print("⚡️ [syncStepsRecent] \(start) → \(now)")
            let raw = await withCheckedContinuation { cont in
                self.hk.fetchStepData(start: start, end: now, intervalMinutes: 5) {
                    cont.resume(returning: $0)
                }
            }
            let existing = await self.sync.fetchExistingStepDates()
            let existingSet = Set(existing.map { Calendar.current.startOfMinute(for: $0) })
            var uploaded = 0
            for s in raw.sorted(by: { $0.date < $1.date }) where s.steps > 0 {
                let m = Calendar.current.startOfMinute(for: s.date)
                guard !existingSet.contains(m) else { continue }
                await self.sync.uploadStep(timestamp: s.date, steps: s.steps)
                uploaded += 1
            }
            await MainActor.run { self.stepsState = .upToDate(now) }
            print("✅ [syncStepsRecent] uploaded \(uploaded) new")
        }

        func syncGlucoseRecent(daysBack: Int) async {
            glucoseState = .syncing
            let now = Date()
            let start = Calendar.current.date(byAdding: .day, value: -daysBack, to: now)!
            print("⚡️ [syncGlucoseRecent] \(start) → \(now)")
            let samples = await withCheckedContinuation { cont in
                self.hk.fetchGlucoseData(start: start, end: now) {
                    cont.resume(returning: $0)
                }
            }
            let existing = await self.sync.fetchExistingGlucoseDates()
            let existingSet = Set(existing.map { Calendar.current.startOfMinute(for: $0) })
            var uploaded = 0
            for g in samples.sorted(by: { $0.date < $1.date }) {
                let m = Calendar.current.startOfMinute(for: g.date)
                guard !existingSet.contains(m) else { continue }
                await self.sync.uploadGlucose(timestamp: g.date, mgdl: g.value)
                uploaded += 1
            }
            await MainActor.run { self.glucoseState = .upToDate(now) }
            print("✅ [syncGlucoseRecent] uploaded \(uploaded) new")
        }
    }

// Helper
extension Calendar {
    func startOfMinute(for date: Date) -> Date {
        return self.date(from: self.dateComponents([.year, .month, .day, .hour, .minute], from: date))!
    }
}
