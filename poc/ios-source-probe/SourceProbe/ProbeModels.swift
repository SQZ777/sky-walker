import CoreLocation
import Foundation
import SwiftUI
import UniformTypeIdentifiers

enum ProbeScenario: String, CaseIterable, Identifiable {
    case realGPS = "real-gps"
    case skyWalkerUSB = "sky-walker-usb"
    case skyWalkerBleLNS = "sky-walker-ble-lns"
    case iAnyGoGeneral = "ianygo-general"
    case iAnyGoBluetooth = "ianygo-bluetooth"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .realGPS: return "Real GPS"
        case .skyWalkerUSB: return "Sky Walker USB"
        case .skyWalkerBleLNS: return "Sky Walker BLE LNS"
        case .iAnyGoGeneral: return "iAnyGo General"
        case .iAnyGoBluetooth: return "iAnyGo Bluetooth"
        }
    }
}

private func iso8601(_ date: Date) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: date)
}

struct CaptureRecord: Encodable {
    let schemaVersion = 1
    let recordType = "capture"
    let sessionID: String
    let scenario: String
    let captureStartedAt: String
    let captureStoppedAt: String
    let iosVersion: String
    let sourceProbeBuild: String

    init(
        sessionID: String,
        scenario: ProbeScenario,
        captureStartedAt: Date,
        captureStoppedAt: Date,
        iosVersion: String,
        sourceProbeBuild: String
    ) {
        self.sessionID = sessionID
        self.scenario = scenario.rawValue
        self.captureStartedAt = iso8601(captureStartedAt)
        self.captureStoppedAt = iso8601(captureStoppedAt)
        self.iosVersion = iosVersion
        self.sourceProbeBuild = sourceProbeBuild
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case recordType = "record_type"
        case sessionID = "session_id"
        case scenario
        case captureStartedAt = "capture_started_at"
        case captureStoppedAt = "capture_stopped_at"
        case iosVersion = "ios_version"
        case sourceProbeBuild = "source_probe_build"
    }
}

struct LocationRecord: Encodable {
    let schemaVersion = 1
    let recordType = "location"
    let sessionID: String
    let scenario: String
    let callbackSequence: Int
    let locationIndex: Int
    let locationTimestamp: String
    let receiptTimestamp: String
    let latitude: Double
    let longitude: Double
    let altitude: Double
    let horizontalAccuracy: Double
    let verticalAccuracy: Double
    let speed: Double
    let course: Double
    let sourceInformationPresent: Bool
    let isSimulatedBySoftware: Bool?
    let isProducedByAccessory: Bool?

    init(
        location: CLLocation,
        sessionID: String,
        scenario: ProbeScenario,
        callbackSequence: Int,
        locationIndex: Int,
        receiptTimestamp: Date
    ) {
        let source = location.sourceInformation
        self.sessionID = sessionID
        self.scenario = scenario.rawValue
        self.callbackSequence = callbackSequence
        self.locationIndex = locationIndex
        self.locationTimestamp = iso8601(location.timestamp)
        self.receiptTimestamp = iso8601(receiptTimestamp)
        self.latitude = location.coordinate.latitude
        self.longitude = location.coordinate.longitude
        self.altitude = location.altitude
        self.horizontalAccuracy = location.horizontalAccuracy
        self.verticalAccuracy = location.verticalAccuracy
        self.speed = location.speed
        self.course = location.course
        self.sourceInformationPresent = source != nil
        self.isSimulatedBySoftware = source?.isSimulatedBySoftware
        self.isProducedByAccessory = source?.isProducedByAccessory
    }

    static func fromCallback(
        _ locations: [CLLocation],
        sessionID: String,
        scenario: ProbeScenario,
        callbackSequence: Int,
        receiptTimestamp: Date
    ) -> [LocationRecord] {
        locations.enumerated().map { index, location in
            LocationRecord(
                location: location,
                sessionID: sessionID,
                scenario: scenario,
                callbackSequence: callbackSequence,
                locationIndex: index,
                receiptTimestamp: receiptTimestamp
            )
        }
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case recordType = "record_type"
        case sessionID = "session_id"
        case scenario
        case callbackSequence = "callback_sequence"
        case locationIndex = "location_index"
        case locationTimestamp = "location_timestamp"
        case receiptTimestamp = "receipt_timestamp"
        case latitude
        case longitude
        case altitude
        case horizontalAccuracy = "horizontal_accuracy"
        case verticalAccuracy = "vertical_accuracy"
        case speed
        case course
        case sourceInformationPresent = "source_information_present"
        case isSimulatedBySoftware = "is_simulated_by_software"
        case isProducedByAccessory = "is_produced_by_accessory"
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(recordType, forKey: .recordType)
        try container.encode(sessionID, forKey: .sessionID)
        try container.encode(scenario, forKey: .scenario)
        try container.encode(callbackSequence, forKey: .callbackSequence)
        try container.encode(locationIndex, forKey: .locationIndex)
        try container.encode(locationTimestamp, forKey: .locationTimestamp)
        try container.encode(receiptTimestamp, forKey: .receiptTimestamp)
        try container.encode(latitude, forKey: .latitude)
        try container.encode(longitude, forKey: .longitude)
        try container.encode(altitude, forKey: .altitude)
        try container.encode(horizontalAccuracy, forKey: .horizontalAccuracy)
        try container.encode(verticalAccuracy, forKey: .verticalAccuracy)
        try container.encode(speed, forKey: .speed)
        try container.encode(course, forKey: .course)
        try container.encode(sourceInformationPresent, forKey: .sourceInformationPresent)
        try container.encode(isSimulatedBySoftware, forKey: .isSimulatedBySoftware)
        try container.encode(isProducedByAccessory, forKey: .isProducedByAccessory)
    }
}

enum ProbeJSONL {
    static func encode(capture: CaptureRecord, locations: [LocationRecord]) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        var lines = [try encoder.encode(capture)]
        lines.append(contentsOf: try locations.map { try encoder.encode($0) })
        var data = Data()
        for line in lines {
            data.append(line)
            data.append(0x0A)
        }
        return data
    }
}

struct ProbeJSONLDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.plainText] }

    let data: Data

    init(data: Data) {
        self.data = data
    }

    init(configuration: ReadConfiguration) throws {
        guard let data = configuration.file.regularFileContents else {
            throw CocoaError(.fileReadCorruptFile)
        }
        self.data = data
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: data)
    }
}
