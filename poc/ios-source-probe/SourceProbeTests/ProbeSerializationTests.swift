import CoreLocation
import Foundation
import XCTest
@testable import SourceProbe

final class ProbeSerializationTests: XCTestCase {
    func testJSONLPreservesEveryCallbackLocationAndNilSourceInformation() throws {
        let timestamp = Date(timeIntervalSince1970: 1_776_124_800)
        let source = CLLocationSourceInformation(
            softwareSimulationState: false,
            andExternalAccessoryState: true
        )
        let accessoryLocation = CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 25.073944586589487, longitude: 121.51104972333346),
            altitude: 5,
            horizontalAccuracy: 3,
            verticalAccuracy: 4,
            course: 90,
            courseAccuracy: 2,
            speed: 1.4,
            speedAccuracy: 0.2,
            timestamp: timestamp,
            sourceInfo: source
        )
        let noSourceLocation = CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 25.0740, longitude: 121.5111),
            altitude: 6,
            horizontalAccuracy: 5,
            verticalAccuracy: -1,
            course: -1,
            speed: -1,
            timestamp: timestamp
        )
        let records = LocationRecord.fromCallback(
            [accessoryLocation, noSourceLocation],
            sessionID: "ABCD2345",
            scenario: .iAnyGoBluetooth,
            callbackSequence: 7,
            receiptTimestamp: timestamp.addingTimeInterval(0.25)
        )
        let capture = CaptureRecord(
            sessionID: "ABCD2345",
            scenario: .iAnyGoBluetooth,
            captureStartedAt: timestamp,
            captureStoppedAt: timestamp.addingTimeInterval(20),
            iosVersion: "26.4",
            sourceProbeBuild: "1"
        )

        let data = try ProbeJSONL.encode(capture: capture, locations: records)
        let lines = String(decoding: data, as: UTF8.self).split(separator: "\n")
        XCTAssertEqual(lines.count, 3)

        let first = try jsonObject(lines[1])
        XCTAssertEqual(first["callback_sequence"] as? Int, 7)
        XCTAssertEqual(first["location_index"] as? Int, 0)
        XCTAssertEqual(first["source_information_present"] as? Bool, true)
        XCTAssertEqual(first["is_simulated_by_software"] as? Bool, false)
        XCTAssertEqual(first["is_produced_by_accessory"] as? Bool, true)

        let second = try jsonObject(lines[2])
        XCTAssertEqual(second["location_index"] as? Int, 1)
        XCTAssertEqual(second["source_information_present"] as? Bool, false)
        XCTAssertTrue(second["is_simulated_by_software"] is NSNull)
        XCTAssertTrue(second["is_produced_by_accessory"] is NSNull)
        XCTAssertEqual(second["vertical_accuracy"] as? Double, -1)
        XCTAssertEqual(second["speed"] as? Double, -1)
        XCTAssertEqual(second["course"] as? Double, -1)
    }

    private func jsonObject(_ line: Substring) throws -> [String: Any] {
        let data = Data(line.utf8)
        return try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
    }
}
