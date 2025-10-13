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
    
    @Published var lastSyncTime: Date? = nil
    @Published var lastSyncRange: String = ""


    // UserDefaults keys
    private let lastStepsKey   = "lastStepsUploadedAt"
    private let lastGlucoseKey = "lastGlucoseUploadedAt"
    private let lastSleepKey   = "lastSleepUploadedAt"
    private let lastEnergyKey  = "lastEnergyUploadedAt"
    private let lastHeartKey   = "lastHeartUploadedAt"
    private let lastBodyKey    = "lastBodyUploadedAt"

    private func last(_ key: String) -> Date? { UserDefaults.standard.object(forKey: key) as? Date }
    private func set(_ key: String, _ d: Date) { UserDefaults.standard.set(d, forKey: key) }

    // MARK: - Entrypoints

    @MainActor
    func bigSync(monthsBack: Int = 12) async {
        let now = Date()
        let start = cal.date(byAdding: .month, value: -monthsBack, to: now)!

        print("🕓 Running Big Sync \(monthsBack)m back → \(start.formatted()) → \(now.formatted())")

        await withTaskGroup(of: Void.self) { group in
            group.addTask { await self.syncSteps(start: start, end: now) }
            group.addTask { await self.syncGlucose(start: start, end: now) }
            group.addTask { await self.syncSleep(start: start, end: now) }
            group.addTask { await self.syncEnergy(start: start, end: now) }
            group.addTask { await self.syncHeart(start: start, end: now) }
            group.addTask { await self.syncBody(start: start, end: now) }
        }

        print("✅ Big Sync complete")

        // 🆕 Record sync metadata
        lastSyncTime = now
        lastSyncRange = "Past \(monthsBack) months"
        persistSyncMeta()
    }

    @MainActor
    func syncRecentDay() async {
        print("⚡️ Running 24h auto-sync for all major metrics…")
        let now = Date()
        let start = cal.date(byAdding: .day, value: -1, to: now)!
        let end = cal.date(byAdding: .day, value: 1, to: cal.startOfDay(for: now))!

        await withTaskGroup(of: Void.self) { group in
            group.addTask { await self.syncSteps(start: start, end: end) }
            group.addTask { await self.syncGlucose(start: start, end: end) }
            group.addTask { await self.syncSleep(start: start, end: end) }
            group.addTask { await self.syncEnergy(start: start, end: end) }
            group.addTask { await self.syncHeart(start: start, end: end) }
            group.addTask { await self.syncBody(start: start, end: end) }
        }

        // 🆕 Record sync metadata
        lastSyncTime = now
        lastSyncRange = "Past 24 hours"
        persistSyncMeta()
    }

    // Optional: persist between launches
    func persistSyncMeta() {
        UserDefaults.standard.set(lastSyncTime, forKey: "lastSyncTime")
        UserDefaults.standard.set(lastSyncRange, forKey: "lastSyncRange")
    }

    // Load persisted data at startup
    init() {
        // ... existing init ...
        if let savedDate = UserDefaults.standard.object(forKey: "lastSyncTime") as? Date {
            self.lastSyncTime = savedDate
        }
        self.lastSyncRange = UserDefaults.standard.string(forKey: "lastSyncRange") ?? ""
    }

    // MARK: - Steps
    func syncSteps(start: Date, end: Date) async {
        stepsState = .syncing
        print("📆 [syncSteps] \(start) → \(end)")
        do {
            let raw = await withCheckedContinuation { cont in
                hk.fetchStepData(start: start, end: end, intervalMinutes: 5) { cont.resume(returning: $0) }
            }

            let existing = await sync.fetchExistingStepDates()
            let existingSet = Set(existing.map { cal.startOfMinute(for: $0) })
            var uploaded = 0

            for s in raw.sorted(by: { $0.date < $1.date }) where s.steps > 0 {
                let minute = cal.startOfMinute(for: s.date)
                guard !existingSet.contains(minute) else { continue }
                await sync.uploadStep(timestamp: minute, steps: s.steps)
                uploaded += 1
            }

            set(lastStepsKey, end)
            stepsState = .upToDate(Date())
            print("✅ [syncSteps] uploaded \(uploaded) new")
        } catch {
            stepsState = .error(error.localizedDescription)
        }
    }

    // MARK: - Glucose
    func syncGlucose(start: Date, end: Date) async {
        glucoseState = .syncing
        print("📆 [syncGlucose] \(start) → \(end)")
        do {
            let samples = await withCheckedContinuation { cont in
                hk.fetchGlucoseData(start: start, end: end) { cont.resume(returning: $0) }
            }

            let existing = await sync.fetchExistingGlucoseDates()
            let existingSet = Set(existing.map { cal.startOfMinute(for: $0) })
            var uploaded = 0

            for g in samples.sorted(by: { $0.date < $1.date }) {
                let minute = cal.startOfMinute(for: g.date)
                guard !existingSet.contains(minute) else { continue }
                await sync.uploadGlucose(timestamp: g.date, mgdl: g.value)
                uploaded += 1
            }

            set(lastGlucoseKey, end)
            glucoseState = .upToDate(Date())
            print("✅ [syncGlucose] uploaded \(uploaded) new")
        } catch {
            glucoseState = .error(error.localizedDescription)
        }
    }

    // MARK: - Sleep
    func syncSleep(start: Date, end: Date) async {
        sleepState = .syncing
        print("😴 [syncSleep] \(start) → \(end)")
        do {
            let episodes = await withCheckedContinuation { cont in
                hk.fetchSleepEpisodes(start: start, end: end) { cont.resume(returning: $0) }
            }

            struct Totals { var inBed=0.0, core=0.0, deep=0.0, rem=0.0, asleep=0.0 }
            var byDay: [Date: Totals] = [:]

            for e in episodes {
                let dur = e.end.timeIntervalSince(e.start) / 60.0
                let wakeDay = cal.startOfDay(for: e.end)
                var t = byDay[wakeDay, default: Totals()]
                switch e.stage.lowercased() {
                case "inbed": t.inBed += dur
                case "core": t.core += dur; t.asleep += dur
                case "deep": t.deep += dur; t.asleep += dur
                case "rem":  t.rem += dur;  t.asleep += dur
                default:
                    t.asleep += dur
                }
                byDay[wakeDay] = t
            }

            if let s = episodes.first { print("🛌 Sample stage:", s.stage) }

            let existingDays = await sync.fetchExistingSleepDays()
            let existingSet = Set(existingDays.map { cal.startOfDay(for: $0) })

            var uploaded = 0
            for (day, t) in byDay.sorted(by: { $0.key < $1.key }) {
                guard !existingSet.contains(day) else { continue }
                await sync.uploadSleepDaily(
                    date: day,
                    totalMin: t.asleep,
                    remMin: t.rem,
                    deepMin: t.deep,
                    coreMin: t.core,
                    inBedMin: t.inBed
                )
                uploaded += 1
            }

            set(lastSleepKey, end)
            sleepState = .upToDate(Date())
            print("✅ [syncSleep] uploaded \(uploaded) new")
        } catch {
            sleepState = .error(error.localizedDescription)
        }
    }

    // MARK: - Energy
    func syncEnergy(start: Date, end: Date) async {
        energyState = .syncing
        print("🔥 [syncEnergy] \(start) → \(end)")
        do {
            async let active: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                hk.fetchActiveEnergyDaily(start: start, end: end) { cont.resume(returning: $0) }
            }
            async let basal: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                hk.fetchBasalEnergyDaily(start: start, end: end) { cont.resume(returning: $0) }
            }

            let (a, b) = await (active, basal)
            let existingDays = await sync.fetchExistingEnergyDays()
            let existingSet = Set(existingDays.map { cal.startOfDay(for: $0) })

            let allDays = Set(a.map { cal.startOfDay(for: $0.date) })
                .union(b.map { cal.startOfDay(for: $0.date) })

            var uploaded = 0
            for day in allDays.sorted() {
                guard !existingSet.contains(day) else { continue }
                let activeKcal = a.first(where: { cal.startOfDay(for: $0.date) == day })?.value ?? 0
                let basalKcal  = b.first(where: { cal.startOfDay(for: $0.date) == day })?.value ?? 0
                await sync.uploadEnergyDaily(date: day, activeKcal: activeKcal, basalKcal: basalKcal)
                uploaded += 1
            }

            set(lastEnergyKey, end)
            energyState = .upToDate(Date())
            print("✅ [syncEnergy] uploaded \(uploaded) new")
        } catch {
            energyState = .error(error.localizedDescription)
        }
    }

    // MARK: - Heart
    func syncHeart(start: Date, end: Date) async {
        heartState = .syncing
        print("❤️ [syncHeart] \(start) → \(end)")
        do {
            async let rhr: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                hk.fetchRestingHRDaily(start: start, end: end) { cont.resume(returning: $0) }
            }
            async let hrv: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                hk.fetchHRVDaily(start: start, end: end) { cont.resume(returning: $0) }
            }
            async let vo2: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                hk.fetchVO2MaxDaily(start: start, end: end) { cont.resume(returning: $0) }
            }

            let (r, h, v) = await (rhr, hrv, vo2)
            let existingDays = await sync.fetchExistingHeartDays()

            // --- define UTC calendar
            var utcCal = Calendar(identifier: .gregorian)
            utcCal.timeZone = TimeZone(secondsFromGMT: 0)!

            // --- build UTC sets
            let existingSet = Set(existingDays.map { utcCal.startOfDay(for: $0) })
            let allDays = Set(
                r.map { utcCal.startOfDay(for: $0.date) } +
                h.map { utcCal.startOfDay(for: $0.date) } +
                v.map { utcCal.startOfDay(for: $0.date) }
            )

            print("❤️ RHR days:", r.count, "HRV days:", h.count, "VO₂Max days:", v.count)
            hk.debugListRestingHR(start: start, end: end)

            var uploaded = 0
            for dayUTC in allDays.sorted() {
                let rhrBpm = r.first(where: { utcCal.isDate($0.date, inSameDayAs: dayUTC) })?.value
                let hrvMs  = h.first(where: { utcCal.isDate($0.date, inSameDayAs: dayUTC) })?.value
                let vo2mx  = v.first(where: { utcCal.isDate($0.date, inSameDayAs: dayUTC) })?.value

                await self.sync.uploadHeartDaily(
                    date: dayUTC,
                    restingHR: rhrBpm,
                    hrvSDNNms: hrvMs,
                    vo2max: vo2mx
                )

                if rhrBpm != nil || hrvMs != nil || vo2mx != nil {
                    uploaded += 1
                }
            }

            set(lastHeartKey, end)
            heartState = .upToDate(Date())
            print("✅ [syncHeart] uploaded \(uploaded) new")

        }
    }

    // MARK: - Body
    func syncBody(start: Date, end: Date) async {
        bodyState = .syncing
        print("⚖️ [syncBody] \(start) → \(end)")
        do {
            async let w: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                hk.fetchWeightDaily(start: start, end: end) { cont.resume(returning: $0) }
            }
            async let f: [HealthKitManager.DailyValue] = withCheckedContinuation { cont in
                hk.fetchBodyFatDaily(start: start, end: end) { cont.resume(returning: $0) }
            }

            let (weights, fats) = await (w, f)
            let existingDays = await sync.fetchExistingBodyDays()
            let existingSet = Set(existingDays.map { cal.startOfDay(for: $0) })

            let allDays = Set(weights.map { cal.startOfDay(for: $0.date) })
                .union(fats.map { cal.startOfDay(for: $0.date) })

            var uploaded = 0
            for day in allDays.sorted() {
                guard !existingSet.contains(day) else { continue }
                let kg  = weights.first(where: { cal.startOfDay(for: $0.date) == day })?.value
                let pct = fats.first(where: { cal.startOfDay(for: $0.date) == day })?.value
                await sync.uploadBodyDaily(date: day, weightKg: kg, bodyFatPct: pct)
                uploaded += 1
            }

            set(lastBodyKey, end)
            bodyState = .upToDate(Date())
            print("✅ [syncBody] uploaded \(uploaded) new")
        } catch {
            bodyState = .error(error.localizedDescription)
        }
        
    }
    
    
}

// MARK: - Helpers
extension Calendar {
    func startOfMinute(for date: Date) -> Date {
        self.date(from: self.dateComponents([.year, .month, .day, .hour, .minute], from: date))!
    }
}
