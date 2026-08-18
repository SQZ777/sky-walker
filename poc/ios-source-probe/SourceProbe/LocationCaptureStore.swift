import Combine
import CoreLocation
import Foundation
import UIKit

@MainActor
final class LocationCaptureStore: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published private(set) var authorizationStatus: CLAuthorizationStatus
    @Published private(set) var isCapturing = false
    @Published private(set) var callbackCount = 0
    @Published private(set) var locationCount = 0
    @Published private(set) var lastRecord: LocationRecord?
    @Published private(set) var exportDocument: ProbeJSONLDocument?
    @Published private(set) var exportFilename = "source-probe.jsonl"
    @Published private(set) var lastError: String?

    private let manager = CLLocationManager()
    private var records: [LocationRecord] = []
    private var activeSessionID = ""
    private var activeScenario = ProbeScenario.realGPS
    private var captureStartedAt: Date?
    private var timeoutTask: Task<Void, Never>?

    override init() {
        authorizationStatus = manager.authorizationStatus
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = kCLDistanceFilterNone
        manager.pausesLocationUpdatesAutomatically = false
    }

    var isAuthorizedWhenInUse: Bool {
        authorizationStatus == .authorizedWhenInUse || authorizationStatus == .authorizedAlways
    }

    func requestAuthorization() {
        manager.requestWhenInUseAuthorization()
    }

    func startCapture(sessionID: String, scenario: ProbeScenario) {
        guard isAuthorizedWhenInUse, !isCapturing else { return }
        activeSessionID = sessionID
        activeScenario = scenario
        captureStartedAt = Date()
        records = []
        callbackCount = 0
        locationCount = 0
        lastRecord = nil
        exportDocument = nil
        lastError = nil
        isCapturing = true
        manager.startUpdatingLocation()
        timeoutTask = Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: 120_000_000_000)
            } catch {
                return
            }
            self?.stopCapture()
        }
    }

    func stopCapture() {
        guard isCapturing, let startedAt = captureStartedAt else { return }
        manager.stopUpdatingLocation()
        timeoutTask?.cancel()
        timeoutTask = nil
        isCapturing = false

        let stoppedAt = Date()
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown"
        let capture = CaptureRecord(
            sessionID: activeSessionID,
            scenario: activeScenario,
            captureStartedAt: startedAt,
            captureStoppedAt: stoppedAt,
            iosVersion: UIDevice.current.systemVersion,
            sourceProbeBuild: build
        )
        do {
            exportDocument = ProbeJSONLDocument(
                data: try ProbeJSONL.encode(capture: capture, locations: records)
            )
            exportFilename = "source-probe-\(activeSessionID)-\(filenameTimestamp(stoppedAt)).jsonl"
        } catch {
            lastError = "Could not prepare JSONL: \(error.localizedDescription)"
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard isCapturing else { return }
        callbackCount += 1
        let callbackRecords = LocationRecord.fromCallback(
            locations,
            sessionID: activeSessionID,
            scenario: activeScenario,
            callbackSequence: callbackCount,
            receiptTimestamp: Date()
        )
        records.append(contentsOf: callbackRecords)
        locationCount += callbackRecords.count
        lastRecord = callbackRecords.last
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        authorizationStatus = manager.authorizationStatus
        if !isAuthorizedWhenInUse && isCapturing {
            lastError = "Location authorization was removed during capture."
            stopCapture()
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        lastError = error.localizedDescription
    }

    private func filenameTimestamp(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return formatter.string(from: date)
    }
}
