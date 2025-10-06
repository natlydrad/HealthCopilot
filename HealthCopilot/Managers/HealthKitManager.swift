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

    func fetchStepData(start: Date, end: Date, completion: @escaping ([StepSample]) -> Void) {
        guard let qt = HKQuantityType.quantityType(forIdentifier: .stepCount) else { return completion([]) }
        let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)
        let q = HKSampleQuery(sampleType: qt, predicate: pred, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, _ in
            var out: [StepSample] = []
            for s in samples as? [HKQuantitySample] ?? [] {
                let steps = s.quantity.doubleValue(for: .count())
                out.append(StepSample(date: s.startDate, steps: Int(steps)))
            }
            DispatchQueue.main.async { completion(out.sorted{ $0.date < $1.date }) }
        }
        store.execute(q)
    }

    // 5-min binning to line up with CGM
    func binSteps(_ raw: [StepSample], intervalMinutes: Int = 5) -> [StepSample] {
        guard let first = raw.first?.date, let last = raw.last?.date else { return [] }
        var bins: [StepSample] = []
        var cursor = first
        while cursor < last {
            let next = cursor.addingTimeInterval(TimeInterval(intervalMinutes * 60))
            let sum = raw.lazy.filter { $0.date >= cursor && $0.date < next }.map(\.steps).reduce(0,+)
            bins.append(StepSample(date: cursor, steps: sum))
            cursor = next
        }
        return bins
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
