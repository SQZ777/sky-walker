# [Spike + PoC] 驗證 Windows 驅動的 iPhone Accessory Attribution

**Status:** ready-for-agent

## Problem Statement

Sky Walker 目前透過 Windows 上的 Apple developer service 對實體 iPhone 執行 USB Location Override。這能提供可控制的測試位置，但不能涵蓋「iPhone 從外接 GPS 配件取得位置」的測試情境，也不能證明 Core Location 會把位置標記為由配件產生。

測試人員需要一個可重複、可稽核的方法，比較真實 GPS、Sky Walker USB Location Override、iAnyGo General Mode 與 iAnyGo Bluetooth Game Mode 所產生的 Core Location 來源資訊，尤其是 `isSimulatedBySoftware`、`isProducedByAccessory` 及 `sourceInformation == nil`。在投入 Windows Bluetooth server 或購買 MFi Simulation Bridge 前，團隊必須先取得實體 iPhone 的來源旗標證據，避免依行銷描述或未公開協定做錯誤架構投資。

## Solution

建立一個 Windows-first 的來源基準測試流程。iPhone 上的 Source Probe 原樣記錄 Core Location callback，輸出版本化 JSONL；Windows 上的實驗性 CLI 建立 Source Test Session、產生 manifest、引導操作、驗證匯出的證據並產生 pass／fail／inconclusive Probe Verdict。Mac 只作為 Apple 官方 Xcode 工具鏈的 Build Station，用於建置、簽署及安裝 Source Probe，不參與日常測試執行。

第一個垂直切片只完成 Source Probe、Windows CLI、schema、驗證器、測試 fixtures 與 Mac 建置指引。先以 real GPS 打通端到端流程，再依序測試 Sky Walker USB、iAnyGo General Mode 與 iAnyGo Bluetooth Game Mode。取得 iAnyGo Bluetooth 的 Accessory Attribution 證據以前，不建立 Windows Bluetooth server，也不採購 MFi Simulation Bridge。

## User Stories

1. As a Windows iOS developer, I want to create a Source Test Session from Windows, so that Windows remains the primary experiment control plane.
2. As a test operator, I want each Source Test Session to have a short unique identifier, so that an exported iPhone log can be matched to the correct manifest.
3. As a test operator, I want to select one of the standard source scenarios, so that real GPS, Sky Walker USB, iAnyGo General, and iAnyGo Bluetooth evidence cannot be confused.
4. As a test operator, I want the Windows CLI to show scenario-specific instructions, so that I can perform the physical-device steps consistently.
5. As a test operator, I want the manifest to record the expected coordinate, so that the validator can confirm that the intended test location actually became active.
6. As a test operator, I want the manifest to record relevant software and OS versions, so that results can be tied to a reproducible environment.
7. As a test operator, I want the Bluetooth scenario to require an explicit USB-disconnected state, so that a USB developer session cannot be mistaken for Bluetooth behavior.
8. As a test operator, I want Windows to independently detect whether an Apple USB device remains connected, so that a checkbox alone cannot produce a false pass.
9. As an iOS tester, I want the Source Probe to request only foreground location permission, so that the PoC does not request unnecessary access.
10. As an iOS tester, I want to enter the Source Test Session ID manually, so that the Probe does not need camera, QR, or live network permissions.
11. As an iOS tester, I want to select the same standard scenario in the Probe, so that the iPhone evidence can be cross-checked with the Windows manifest.
12. As an iOS tester, I want to start and stop a capture explicitly, so that the evidence window has clear boundaries.
13. As an iOS tester, I want to see incoming Core Location callbacks live, so that I can tell whether the selected source is producing data.
14. As an iOS tester, I want every location in every callback preserved, so that the Probe does not hide cached, mixed, or transitional source behavior.
15. As an iOS tester, I want both the location timestamp and receipt timestamp recorded, so that stabilization and stale samples can be evaluated later.
16. As an iOS tester, I want missing source information preserved as nil, so that absence is not silently converted to false.
17. As an iOS tester, I want both source flags recorded independently, so that “not software simulated” is never treated as equivalent to Accessory Attribution.
18. As an iOS tester, I want latitude, longitude, altitude, accuracy, speed, and course preserved, so that later phases can analyze field behavior without repeating the capture.
19. As a privacy-conscious tester, I want evidence files to omit UDID, Apple Account, and Bluetooth MAC data, so that logs can be handled safely.
20. As a test operator, I want one timestamped JSONL file per Source Test Session, so that evidence from separate sources is never interleaved.
21. As a test operator, I want to export the JSONL manually after capture, so that live file transfer cannot affect the Bluetooth source test.
22. As a Windows developer, I want to validate a manifest and JSONL from the CLI, so that the experiment can be evaluated without reopening the iOS app.
23. As a Windows developer, I want schema errors reported separately from source failures, so that malformed evidence is not classified as a failed accessory.
24. As a Windows developer, I want the validator to enforce Session ID and scenario agreement, so that evidence cannot be attached to the wrong run.
25. As a Windows developer, I want the validator to ignore stabilization samples without deleting them from the artifact, so that the verdict is deterministic while the raw evidence remains intact.
26. As a Windows developer, I want a pass to require ten consecutive accessory-produced samples, so that a transient or mixed source cannot produce a false success.
27. As a Windows developer, I want insufficient, mixed, nil-source, or connection-ambiguous evidence classified as inconclusive, so that uncertainty is not mislabeled as failure.
28. As a Windows developer, I want complete evidence with consistently false accessory flags classified as fail, so that a tested source can be rejected clearly.
29. As a Windows developer, I want a machine-readable verdict as well as a human summary, so that later automation can consume the same decision.
30. As a Windows developer, I want distinct process exit statuses for pass, fail, inconclusive, and invalid input, so that scripts can react reliably.
31. As a researcher, I want all four source scenarios to use the same initial coordinate and fallback route, so that source type is the principal changed variable.
32. As a researcher, I want the initial benchmark to require only reasonable horizontal agreement, so that source attribution is not blocked by fields that are not yet controllable.
33. As a researcher, I want iAnyGo treated as a black box, so that the project can measure its public behavior without copying a private protocol.
34. As a researcher, I want a positive iAnyGo Bluetooth result to trigger licensing and public-protocol research, so that implementation remains legal and maintainable.
35. As a researcher, I want a negative or nil iAnyGo Bluetooth result to stop that implementation direction, so that the project does not imitate a product that fails the required criterion.
36. As a maintainer, I want raw device evidence excluded from version control, so that accidental device-data disclosure is less likely.
37. As a maintainer, I want de-identified fixtures checked in, so that schema and verdict behavior can be tested deterministically.
38. As a maintainer, I want the Source Probe to use only Apple system frameworks, so that the PoC has no unnecessary iOS package dependencies.
39. As a maintainer, I want Accessory Feed kept separate from USB Location Override, so that their Session, Stop Feed, Clear, and failure semantics remain honest.
40. As a Windows-first developer, I want Mac use limited to build and signing steps, so that normal experiment execution never depends on macOS.
41. As a developer using a free Personal Team, I want documented reprovisioning steps, so that the seven-day signing expiration is predictable.
42. As a project owner, I want the real-GPS round trip completed before vendor benchmarks, so that failures in the Probe pipeline are separated from failures in location products.
43. As a project owner, I want the Windows Bluetooth server deferred until the benchmark is known, so that engineering effort follows evidence.
44. As a project owner, I want MFi hardware retained as a fallback rather than an immediate purchase, so that hardware cost is incurred only when justified.

## Implementation Decisions

- **Product boundary:** Accessory Feed is a distinct capability from Location Override. An Accessory Feed Session stops with Stop Feed; it does not use Clear and does not promise that iOS immediately returns to internal GPS.
- **Phase gate:** This spec is an evidence-gathering Spike and PoC. A supported implementation, an MFi bridge architecture, or documented platform infeasibility are all valid final outcomes.
- **Windows-first architecture:** Windows owns experiment creation, scenario guidance, environment capture, artifact validation, verdict generation, and future transport work.
- **iPhone observation plane:** Source Probe observes Core Location only. It never creates replacement locations or injects source metadata.
- **Mac build-only role:** Mac and Xcode are required only to build, sign, install, and periodically reprovision Source Probe. There is no macOS location-control implementation.
- **PoC isolation:** The Windows benchmark lives in an isolated accessory-probe module with an explicitly experimental CLI surface. It may reuse configuration and device-detection capabilities but does not call the USB Location Override backend or GUI.
- **CLI creation contract:** A `probe new` operation accepts a standard scenario, creates an eight-character Source Test Session ID, writes a versioned manifest, and prints the physical test steps.
- **CLI validation contract:** A `probe validate` operation accepts one manifest and one JSONL artifact, validates their relationship and environment evidence, and emits both human-readable and machine-readable results.
- **Standard scenarios:** The supported values are real GPS, Sky Walker USB, iAnyGo General, and iAnyGo Bluetooth. Arbitrary free-form source labels are not accepted in the first version.
- **Schema versioning:** Manifest and callback records carry schema version 1. Callback records reference the Source Test Session ID.
- **Manifest contents:** The manifest contains scenario, expected coordinate, session timing, iOS and app builds, Windows version, relevant location-product version, Bluetooth adapter information when applicable, and user-confirmed connection state.
- **Callback contents:** Each record contains location timestamp, receipt timestamp, coordinates, altitude, horizontal and vertical accuracy, speed, course, source-information presence, and both Core Location source flags.
- **Raw evidence preservation:** Every `CLLocation` in every delegate callback is written. The Probe does not keep only the last element and does not pre-filter stale or transitional samples.
- **Location Manager configuration:** Capture uses best accuracy, no distance filter, and disables automatic pausing while a Source Test Session is active.
- **Minimal iOS UI:** Source Probe provides scenario selection, Session ID entry, Start, Stop, live callback visibility, and export. It has no map and no background-location mode.
- **Native iOS project:** The Probe is a minimal native SwiftUI application using Core Location. It does not use XcodeGen, CocoaPods, or third-party Swift packages.
- **Manual artifact transfer:** The first version exports through the system Share or Files UI after the test. Live networking and USB artifact retrieval are deferred.
- **USB proof:** iAnyGo Bluetooth validation requires both a user confirmation and an independent Windows PnP check showing no physical Apple USB connection. A detected USB connection prevents pass.
- **Stabilization window:** Validation excludes the first ten seconds from verdict calculation while preserving those records in the raw artifact.
- **Sample requirement:** Validation needs at least ten post-stabilization callbacks and waits no longer than 120 seconds during capture guidance.
- **Accessory pass rule:** Pass requires at least ten consecutive post-stabilization records with non-nil source information and `isProducedByAccessory == true`, plus satisfied Bluetooth USB-disconnection evidence where relevant.
- **Fail rule:** Fail requires structurally complete evidence, a confirmed scenario, enough samples, an active expected location, and consistently false accessory attribution.
- **Inconclusive rule:** Insufficient samples, mixed flags, nil source information, uncertain USB state, missing environment metadata, or an inactive expected location are inconclusive rather than fail.
- **Coordinate sanity gate:** The first benchmark requires the observed position to be within 25 metres horizontally of the expected position. Altitude, speed, course, and reported accuracy are recorded but do not determine the initial Probe Verdict.
- **Common stimulus:** Each scenario first uses the project Default Location. If static delivery cannot produce ten callbacks, it uses the same approximately 50-metre two-point route at 1 Hz and about 5 km/h.
- **Evidence storage:** Raw run artifacts are locally retained outside version control. Only manually de-identified fixtures are committed.
- **iAnyGo boundary:** Only the official trial on test equipment is used. The experiment does not intercept payloads, reverse engineer binaries or protocols, log into sensitive accounts, or reproduce private behavior.
- **Positive iAnyGo branch:** If iAnyGo Bluetooth demonstrates Accessory Attribution, the next step is to identify a public or legitimately licensed implementation path before any server work.
- **Negative iAnyGo branch:** If iAnyGo Bluetooth produces false accessory flags or nil source information, it is not the required baseline; that implementation direction stops and MFi Simulation Bridge sourcing becomes the fallback investigation.
- **Branch baseline:** Implementation begins from the existing desktop-GUI feature baseline on a dedicated accessory-GPS PoC branch, while the first vertical slice remains independent of the GUI.

## Testing Decisions

- **Primary automated seam:** Treat manifest plus JSONL as input and Probe Verdict, summaries, and process status as output. Tests assert externally visible validation behavior rather than helper functions or internal state.
- **Schema coverage:** Test supported version 1 records, unknown versions, missing required metadata, malformed JSONL, duplicate or mismatched Session IDs, and mismatched scenarios.
- **Verdict coverage:** Use de-identified fixtures for pass, fail, insufficient samples, mixed flags, nil source information, active USB, unknown USB state, missing versions, stale samples, and coordinate mismatch.
- **Boundary coverage:** Verify that the first ten seconds never affect the verdict, that raw records remain present, and that exactly ten valid consecutive samples can pass.
- **USB coverage:** Inject the Windows physical-USB detector at the CLI boundary and test present, absent, and detection-error outcomes without requiring real hardware.
- **CLI coverage:** Exercise session creation and validation through the command surface, asserting manifest output, human summary, machine-readable result, and distinct process statuses.
- **iOS serialization seam:** Test the callback-to-record mapper and JSONL writer through their observable serialized output, preserving arrays, timestamps, nil source information, negative or unavailable measurement values, and independent source flags.
- **No mocked Core Location acceptance:** Unit tests cannot establish Accessory Attribution. Only `CLLocationManager` callbacks from a physical iPhone count as source evidence.
- **First end-to-end smoke test:** Build and install Source Probe with Xcode, capture one real-GPS Source Test Session on a physical iPhone, export JSONL, and validate it on Windows.
- **Benchmark order:** After the smoke test, capture Sky Walker USB, iAnyGo General, and iAnyGo Bluetooth in that order on the same device and common stimulus.
- **Prior art:** Follow the repository's existing parametrized pure-logic tests for deterministic validation and its injected-collaborator tests for device and GUI boundaries.
- **Completion rule:** Code and unit tests alone do not complete the first slice. The physical real-GPS round trip and Windows verdict are mandatory.

## Out of Scope

- Implementing a Windows Bluetooth Classic GNSS, RFCOMM, SPP, BLE LNS, iAP, or MFi accessory server before benchmark evidence exists.
- Integrating Accessory Feed into the production GUI.
- Purchasing a Bad Elf or other MFi Simulation Bridge during the first vertical slice.
- Reverse engineering iAnyGo, intercepting its private payload, copying private protocols, bypassing MFi authentication, or using leaked credentials.
- Hiding or falsifying source flags inside the Source Probe.
- Constructing synthetic `CLLocation` objects as acceptance evidence.
- Background location collection, App Store distribution, TestFlight distribution, or paid Apple Developer Program enrollment.
- Live synchronization of Probe records to Windows.
- Automatic USB retrieval of the JSONL artifact.
- Treating altitude, speed, course, vertical accuracy, or requested accuracy as controlled pass criteria in the source-attribution benchmark.
- Supporting arbitrary third-party location applications or guaranteeing their behavior.
- Testing more than the existing physical iPhone in the first vertical slice; a second iOS version remains a later final-acceptance requirement.
- Disabling Windows LSA or other platform security protections.

## Further Notes

- Public Apple documentation identifies Made for iPhone GPS and CarPlay as examples that produce accessory-attributed Core Location data. Public Bluetooth profile documentation does not expose a generic GPS-to-Core-Location path.
- iAnyGo's official workflow demonstrates that a commercial product can pair an iPhone directly with a PC Bluetooth adapter without requiring the user to buy a separate bridge. It does not publish its Bluetooth profile, payload, licensing status, or Core Location source flags.
- These facts are compatible: MFi remains the only publicly documented supported path, while iAnyGo remains an unverified black-box benchmark that may or may not satisfy Accessory Attribution.
- Free Personal Team provisioning is sufficient for physical-device testing but expires after seven days and requires periodic Xcode rebuild and reinstall.
- The full PoC remains successful if it proves direct Windows support, produces a workable licensed/MFi bridge architecture, or documents platform infeasibility with evidence and alternatives.
