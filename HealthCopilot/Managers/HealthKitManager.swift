// HealthKitManager.swift
import HealthKit

final class HealthKitManager {
    static let shared = HealthKitManager()
    private let store = HKHealthStore()
    private init() {}

    func requestPermissions(completion: @escaping (Bool) -> Void) {
        let readTypes: Set = [
            HKObjectType.quantityType(forIdentifier: .bloodGlucose)!,
            HKObjectType.quantityType(forIdentifier: .stepCount)!
        ]
        store.requestAuthorization(toShare: [], read: readTypes) { ok, _ in completion(ok) }
    }

    // You already have this pattern; keep it.
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

    struct StepSample { let date: Date; let steps: Int }

    func fetchStepData(start: Date, end: Date, intervalMinutes: Int = 5,
                       completion: @escaping ([StepSample]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .stepCount) else { return completion([]) }

        var interval = DateComponents()
        interval.minute = intervalMinutes

        let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        // separateBySource keeps iPhone/Watch counts distinct
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

                // examine each source independently
                if let sources = stats.sources {
                    for source in sources {
                        guard let q = stats.sumQuantity(for: source) else { continue }
                        let isWatch = source.name.localizedCaseInsensitiveContains("watch")
                        // prefer Watch if present; otherwise pick max
                        if isWatch && !choseWatch {
                            chosen = q
                            choseWatch = true
                        } else if !choseWatch {
                            if let c = chosen {
                                if q.doubleValue(for: .count()) > c.doubleValue(for: .count()) {
                                    chosen = q
                                }
                            } else {
                                chosen = q
                            }
                        }
                    }
                }

                if let q = chosen {
                    let steps = Int(q.doubleValue(for: .count()))
                    if steps > 0 {
                        out.append(StepSample(date: stats.startDate, steps: steps))
                    }
                }
            }
            DispatchQueue.main.async {
                completion(out.sorted { $0.date < $1.date })
            }
        }

        self.store.execute(q)
    }


    // 5-min binning to line up with CGM
    // Deduped 5-min binning to align with CGM & prevent duplicates
    func binSteps(_ raw: [StepSample], intervalMinutes: Int = 5) -> [StepSample] {
        guard !raw.isEmpty else { return [] }
        let interval = TimeInterval(intervalMinutes * 60)
        var buckets: [Date: Int] = [:]

        for s in raw {
            // Floor timestamp to nearest interval boundary
            let floored = floor(s.date.timeIntervalSinceReferenceDate / interval) * interval
            let bucketDate = Date(timeIntervalSinceReferenceDate: floored)
            buckets[bucketDate, default: 0] += s.steps
        }

        return buckets.keys.sorted().map { StepSample(date: $0, steps: buckets[$0] ?? 0) }
    }

    
    func debugListAllTypes() {
        let quantityTypes: [HKQuantityTypeIdentifier] = [
            .stepCount,
            .bloodGlucose,
            .activeEnergyBurned,
            .heartRate,
            .distanceWalkingRunning
        ]
        
        print("🧬 Checking if these quantity types are available:")
        for id in quantityTypes {
            if let type = HKQuantityType.quantityType(forIdentifier: id) {
                let available = HKHealthStore.isHealthDataAvailable()
                print("• \(id.rawValue): \(available ? "Health data available" : "Not available")")
            } else {
                print("• \(id.rawValue): ❌ not recognized")
            }
        }
    }


}
