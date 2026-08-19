import CoreLocation
import Foundation
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @StateObject private var capture = LocationCaptureStore()
    @State private var sessionID = ""
    @State private var scenario = ProbeScenario.realGPS
    @State private var showingExporter = false
    @State private var exportError: String?

    private var normalizedSessionID: String {
        sessionID.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    }

    private var validSessionID: Bool {
        normalizedSessionID.range(
            of: "^[A-Z2-9]{8}$",
            options: .regularExpression
        ) != nil
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Source Test Session") {
                    TextField("8-character Session ID", text: $sessionID)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                    Picker("Scenario", selection: $scenario) {
                        ForEach(ProbeScenario.allCases) { item in
                            Text(item.title).tag(item)
                        }
                    }
                    LabeledContent("Permission", value: authorizationLabel)
                    if !capture.isAuthorizedWhenInUse {
                        Button("Allow Foreground Location") {
                            capture.requestAuthorization()
                        }
                    }
                }

                Section("Capture") {
                    HStack {
                        Button("Start") {
                            sessionID = normalizedSessionID
                            capture.startCapture(sessionID: normalizedSessionID, scenario: scenario)
                        }
                        .disabled(!validSessionID || !capture.isAuthorizedWhenInUse || capture.isCapturing)

                        Button("Stop") {
                            capture.stopCapture()
                        }
                        .disabled(!capture.isCapturing)
                    }
                    LabeledContent("State", value: capture.isCapturing ? "Capturing" : "Stopped")
                    LabeledContent("Callbacks", value: String(capture.callbackCount))
                    LabeledContent("Locations", value: String(capture.locationCount))
                    Text("Capture stops automatically after 120 seconds. The first 10 seconds remain in the artifact but are excluded by the Windows verdict.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                if let record = capture.lastRecord {
                    Section("Latest CLLocation") {
                        LabeledContent("Latitude", value: String(format: "%.8f", record.latitude))
                        LabeledContent("Longitude", value: String(format: "%.8f", record.longitude))
                        LabeledContent("Source info", value: record.sourceInformationPresent ? "present" : "nil")
                        LabeledContent(
                            "Software simulated",
                            value: optionalBoolean(record.isSimulatedBySoftware)
                        )
                        LabeledContent(
                            "Produced by accessory",
                            value: optionalBoolean(record.isProducedByAccessory)
                        )
                    }
                }

                Section("Export") {
                    Button("Export JSONL") {
                        showingExporter = true
                    }
                    .disabled(capture.exportDocument == nil || capture.isCapturing)
                    if let message = capture.lastError ?? exportError {
                        Text(message).foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Source Probe")
            .fileExporter(
                isPresented: $showingExporter,
                document: capture.exportDocument,
                contentType: .plainText,
                defaultFilename: capture.exportFilename
            ) { result in
                if case let .failure(error) = result {
                    exportError = error.localizedDescription
                }
            }
        }
    }

    private var authorizationLabel: String {
        switch capture.authorizationStatus {
        case .notDetermined: return "Not requested"
        case .restricted: return "Restricted"
        case .denied: return "Denied"
        case .authorizedAlways: return "Always"
        case .authorizedWhenInUse: return "When In Use"
        @unknown default: return "Unknown"
        }
    }

    private func optionalBoolean(_ value: Bool?) -> String {
        guard let value else { return "nil" }
        return value ? "true" : "false"
    }
}

#Preview {
    ContentView()
}
