// HealthKitManager.swift
import HealthKit

final class HealthKitManager {
    static let shared = HealthKitManager()
    private let store = HKHealthStore()
    private init() {}

    // MARK: - Types

    struct GlucoseSample { let date: Date; let value: Double }
    struct StepSample   { let date: Date; let steps: Int }

    struct SleepSample {
        let start: Date
        let end: Date
        /// "inBed", "asleepCore", "asleepDeep", "asleepREM", or "asleep" (fallback)
        let stage: String
    }

    struct DailyValue {
        let date: Date   // local day (00:00)
        let value: Double
    }

    struct DailyPair {
        let date: Date
        let a: Double
        let b: Double
    }

    // MARK: - Permissions

    func requestPermissions(completion: @escaping (Bool) -> Void) {
        var readTypes: Set<HKObjectType> = [
            HKObjectType.quantityType(forIdentifier: .bloodGlucose)!,
            HKObjectType.quantityType(forIdentifier: .stepCount)!
        ]

        // New: Energy
        if let t = HKObjectType.quantityType(forIdentifier: .activeEnergyBurned) { readTypes.insert(t) }
        if let t = HKObjectType.quantityType(forIdentifier: .basalEnergyBurned) { readTypes.insert(t) }

        // New: Heart
        if let t = HKObjectType.quantityType(forIdentifier: .restingHeartRate) { readTypes.insert(t) }
        if let t = HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN) { readTypes.insert(t) }
        if let t = HKObjectType.quantityType(forIdentifier: .vo2Max) { readTypes.insert(t) }

        // New: Body
        if let t = HKObjectType.quantityType(forIdentifier: .bodyMass) { readTypes.insert(t) }
        if let t = HKObjectType.quantityType(forIdentifier: .bodyFatPercentage) { readTypes.insert(t) }

        // New: Sleep
        if let t = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) { readTypes.insert(t) }

        store.requestAuthorization(toShare: [], read: readTypes) { ok, _ in completion(ok) }
    }

    // MARK: - Glucose (unchanged pattern)

    func fetchGlucoseData(start: Date, end: Date, completion: @escaping ([GlucoseSample]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .bloodGlucose) else { return completion([]) }
        let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)
        let q = HKSampleQuery(sampleType: qt, predicate: pred, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, _ in
            var out: [GlucoseSample] = []
            for s in samples as? [HKQuantitySample] ?? [] {
                let val = s.quantity.doubleValue(for: HKUnit(from: "mg/dL"))
                out.append(GlucoseSample(date: s.startDate, value: val))
            }
            DispatchQueue.main.async { completion(out.sorted{ $0.date < $1.date }) }
        }
        store.execute(q)
    }

    // MARK: - Steps (5-min stats, prefer Watch, de-duped)

    func fetchStepData(start: Date, end: Date, intervalMinutes: Int = 5,
                       completion: @escaping ([StepSample]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .stepCount) else { return completion([]) }

        var interval = DateComponents(); interval.minute = intervalMinutes
        let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        let q = HKStatisticsCollectionQuery(
            quantityType: qt,
            quantitySamplePredicate: pred,
            options: [.cumulativeSum, .separateBySource],
            anchorDate: start,
            intervalComponents: interval
        )

        q.initialResultsHandler = { _, results, _ in
            var out: [StepSample] = []
            results?.enumerateStatistics(from: start, to: end) { stats, _ in
                var chosen: HKQuantity?
                var choseWatch = false
                if let sources = stats.sources {
                    for source in sources {
                        guard let q = stats.sumQuantity(for: source) else { continue }
                        let isWatch = source.name.localizedCaseInsensitiveContains("watch")
                        if isWatch && !choseWatch {
                            chosen = q; choseWatch = true
                        } else if !choseWatch {
                            if let c = chosen {
                                if q.doubleValue(for: .count()) > c.doubleValue(for: .count()) {
                                    chosen = q
                                }
                            } else { chosen = q }
                        }
                    }
                }
                if let q = chosen {
                    let steps = Int(q.doubleValue(for: .count()))
                    if steps > 0 { out.append(StepSample(date: stats.startDate, steps: steps)) }
                }
            }
            DispatchQueue.main.async { completion(out.sorted { $0.date < $1.date }) }
        }
        store.execute(q)
    }

    // Align 5-min bins for steps
    func binSteps(_ raw: [StepSample], intervalMinutes: Int = 5) -> [StepSample] {
        guard !raw.isEmpty else { return [] }
        let interval = TimeInterval(intervalMinutes * 60)
        var buckets: [Date: Int] = [:]
        for s in raw {
            let floored = floor(s.date.timeIntervalSinceReferenceDate / interval) * interval
            let bucketDate = Date(timeIntervalSinceReferenceDate: floored)
            buckets[bucketDate, default: 0] += s.steps
        }
        return buckets.keys.sorted().map { StepSample(date: $0, steps: buckets[$0] ?? 0) }
    }

    // MARK: - Sleep (episodes)

    func fetchSleepEpisodes(start: Date, end: Date, completion: @escaping ([SleepSample]) -> Void) {
        guard let ct = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) else { return completion([]) }
        let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        let q = HKSampleQuery(sampleType: ct, predicate: pred, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, _ in
            var out: [SleepSample] = []
            for s in samples as? [HKCategorySample] ?? [] {
                let stage: String
                if #available(iOS 16.0, *) {
                    switch s.value {
                    case HKCategoryValueSleepAnalysis.inBed.rawValue: stage = "inBed"
                    case HKCategoryValueSleepAnalysis.asleepCore.rawValue: stage = "asleepCore"
                    case HKCategoryValueSleepAnalysis.asleepDeep.rawValue: stage = "asleepDeep"
                    case HKCategoryValueSleepAnalysis.asleepREM.rawValue: stage = "asleepREM"
                    case HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue: fallthrough
                    default: stage = "asleep"
                    }
                } else {
                    stage = (s.value == HKCategoryValueSleepAnalysis.inBed.rawValue) ? "inBed" : "asleep"
                }
                out.append(SleepSample(start: s.startDate, end: s.endDate, stage: stage))
            }
            DispatchQueue.main.async { completion(out.sorted{ $0.start < $1.start }) }
        }
        store.execute(q)
    }

    // MARK: - Energy (daily sums)

    func fetchActiveEnergyDaily(start: Date, end: Date, completion: @escaping ([DailyValue]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned) else { return completion([]) }
        dailySum(type: qt, start: start, end: end, unit: .kilocalorie()) { completion($0) }
    }

    func fetchBasalEnergyDaily(start: Date, end: Date, completion: @escaping ([DailyValue]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .basalEnergyBurned) else { return completion([]) }
        dailySum(type: qt, start: start, end: end, unit: .kilocalorie()) { completion($0) }
    }

    // MARK: - Heart (daily averages)

    func fetchRestingHRDaily(start: Date, end: Date, completion: @escaping ([DailyValue]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .restingHeartRate) else { return completion([]) }
        dailyAvg(type: qt, start: start, end: end, unit: HKUnit.count().unitDivided(by: .minute())) { completion($0) }
    }

    func fetchHRVDaily(start: Date, end: Date, completion: @escaping ([DailyValue]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .heartRateVariabilitySDNN) else { return completion([]) }
        dailyAvg(type: qt, start: start, end: end, unit: .secondUnit(with: .milli)) { completion($0) }
    }

    func fetchVO2MaxDaily(start: Date, end: Date, completion: @escaping ([DailyValue]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .vo2Max) else { return completion([]) }
        dailyAvg(type: qt, start: start, end: end, unit: HKUnit(from: "ml/(kg*min)")) { completion($0) }
    }

    // MARK: - Body (daily averages)

    func fetchWeightDaily(start: Date, end: Date, completion: @escaping ([DailyValue]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .bodyMass) else { return completion([]) }
        dailyAvg(type: qt, start: start, end: end, unit: .gramUnit(with: .kilo)) { completion($0) }
    }

    func fetchBodyFatDaily(start: Date, end: Date, completion: @escaping ([DailyValue]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .bodyFatPercentage) else { return completion([]) }
        dailyAvg(type: qt, start: start, end: end, unit: .percent()) { completion($0) }
    }

    // MARK: - Helpers: daily sums / avgs

    private func dailySum(type: HKQuantityType, start: Date, end: Date, unit: HKUnit,
                          completion: @escaping ([DailyValue]) -> Void) {
        var interval = DateComponents(); interval.day = 1
        // anchor at local midnight
        let anchor = Calendar.current.startOfDay(for: start)
        let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)
        let q = HKStatisticsCollectionQuery(quantityType: type, quantitySamplePredicate: pred,
                                            options: [.cumulativeSum], anchorDate: anchor, intervalComponents: interval)
        q.initialResultsHandler = { _, results, _ in
            var out: [DailyValue] = []
            results?.enumerateStatistics(from: start, to: end) { stats, _ in
                if let sum = stats.sumQuantity() {
                    out.append(DailyValue(date: Calendar.current.startOfDay(for: stats.startDate),
                                          value: sum.doubleValue(for: unit)))
                }
            }
            DispatchQueue.main.async { completion(out.sorted{ $0.date < $1.date }) }
        }
        store.execute(q)
    }

    private func dailyAvg(type: HKQuantityType, start: Date, end: Date, unit: HKUnit,
                          completion: @escaping ([DailyValue]) -> Void) {
        var interval = DateComponents(); interval.day = 1
        let anchor = Calendar.current.startOfDay(for: start)
        let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)
        let q = HKStatisticsCollectionQuery(quantityType: type, quantitySamplePredicate: pred,
                                            options: [.discreteAverage], anchorDate: anchor, intervalComponents: interval)
        q.initialResultsHandler = { _, results, _ in
            var out: [DailyValue] = []
            results?.enumerateStatistics(from: start, to: end) { stats, _ in
                if let avg = stats.averageQuantity() {
                    out.append(DailyValue(date: Calendar.current.startOfDay(for: stats.startDate),
                                          value: avg.doubleValue(for: unit)))
                }
            }
            DispatchQueue.main.async { completion(out.sorted{ $0.date < $1.date }) }
        }
        store.execute(q)
    }

    // Debug helper (optional)
    func debugListAllTypes() {
        let quantityTypes: [HKQuantityTypeIdentifier] = [
            .stepCount, .bloodGlucose, .activeEnergyBurned, .basalEnergyBurned,
            .restingHeartRate, .heartRateVariabilitySDNN, .vo2Max, .bodyMass, .bodyFatPercentage
        ]
        print("🧬 Checking Health data availability:", HKHealthStore.isHealthDataAvailable())
        for id in quantityTypes {
            if HKQuantityType.quantityType(forIdentifier: id) != nil {
                print("• \(id.rawValue): OK")
            } else {
                print("• \(id.rawValue): ❌ not recognized")
            }
        }
    }
}