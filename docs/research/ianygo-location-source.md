# iAnyGo 定位來源機制與 `CLLocationSourceInformation` 可行性調查

調查日期：2026-08-18

計畫狀態：本文保留為背景研究；實驗順序已由 ADR-0004 取代。先完成三次有界 BLE LNS 實驗，未通過後才進入使用者批准的 iAnyGo 唯讀行為調查。

## 結論

Tenorshare iAnyGo 足以證明一件事：**使用者不一定要另外購買 Bad Elf／MFi Simulation Bridge，才能讓 iPhone 在一條以電腦 Bluetooth adapter 為端點的專有路徑上收到修改後的位置。** Tenorshare 的 Windows 操作文件要求 iPhone 搜尋、配對 PC 的 Bluetooth 名稱，並要求 PC 的 Bluetooth hardware 與 driver 正常；未要求另外接一個專用 GPS 盒子。

但現有公開證據**不足以證明**下列任一項：

- iAnyGo 的 Bluetooth Game Mode 會讓 `CLLocation.sourceInformation?.isProducedByAccessory == true`。
- 它使用公開 Bluetooth GNSS、NMEA、BLE Location and Navigation Service 或公開 MFi 協定。
- 它的方法可在不使用私有協定、不繞過 MFi、不依賴 Tenorshare 授權元件的前提下重作。
- 行銷所稱的「原生 App 可用」、「not detected」、「natural」或「不依賴 Apple developer platform」等同於任何 Core Location 來源旗標。

因此，iAnyGo **推翻的是「一定要先買一個實體 MFi bridge 才值得繼續研究」**，不是 Apple 公開文件所指向的 MFi 限制。就本專案的合法、公開、可維護實作主線而言，MFi／認證硬體仍是目前唯一有 Apple 一手文件支持的 external-location-over-Bluetooth 路徑；但在採購前，應先用 iAnyGo Bluetooth Game Mode 做一次最小黑箱旗標實驗。

## 證據分級

本文只採用產品或平台擁有者的一手資料：Tenorshare 官方指南與官方安裝檔、Apple 官方文件。Tenorshare 對自家工作流程與系統需求屬一手來源；對「不會被偵測」或「零風險」的行銷主張則不視為 Core Location 技術證據。

## iAnyGo 實際上有多條不同路徑

不能把「iAnyGo」視為單一傳輸機制。官方資料至少顯示下列三類流程。

| 路徑 | 官方可確認的連線／準備 | 能否由公開資料判定來源旗標 |
| --- | --- | --- |
| Desktop General Mode（USB／Wi-Fi） | USB 連線、解鎖與 Trust；Wi-Fi 模式必須先成功用 USB 連過，且手機與 PC 位於同一 Wi-Fi。[Tenorshare 一般模式指南](https://www.tenorshare.com/guide/how-to-change-your-location-on-iphone.html) | 不能。此工作流程很像 host-driven developer location，但官方沒有公開實際 protocol 或旗標紀錄。 |
| Desktop Game Mode（Bluetooth） | iPhone 實際搜尋並配對 PC／Mac；Windows 端使用 PC 的 Bluetooth 名稱、hardware 與 driver。指南未要求另外購買 dongle／bridge。[Tenorshare Bluetooth 連線指南](https://www.tenorshare.com/guide/ianygo-connection-tutorial.html)、[Tenorshare Bluetooth 疑難排解](https://www.tenorshare.com/change-location/bluetooth-tech-pokemon-go-spoofer-update.html) | 不能。官方沒有公開 Bluetooth profile、payload、MFi 狀態或 `CLLocationSourceInformation` callback。 |
| iAnyGo iOS App／Assistant | TestFlight 或側載 App、resource/trust files、IPLocate，以及新增 VPN configuration；不同 iOS 與安裝路徑的 Developer Mode 要求不同。[Tenorshare iOS App 指南](https://www.tenorshare.com/ianygo-ios-app-users-guide.html) | 不能；這是 companion-app／VPN／resource 安裝路徑，不是「PC 模擬外接 GPS」的直接證據。 |

### Desktop General Mode

Tenorshare 的一般指南列出兩種連線：

- USB：接上電腦、解鎖 iPhone，並在提示時信任電腦。
- Wi-Fi：先曾經以 USB 成功連線，PC 與手機位於同一 Wi-Fi，手機螢幕保持開啟。

指南宣稱修改後會影響裝置上的 location-based apps，也標示支援 iOS 26，但沒有說明所用 Apple service。這只能證明產品行為與連線前置條件，不能直接證明它使用 DVT `LocationSimulation`，也不能推出 `isSimulatedBySoftware` 的值。

### Desktop Bluetooth Game Mode

Tenorshare 的 Bluetooth 指南描述的不是「購買一個 Tenorshare GPS 盒子」：

- Windows 流程會偵測 PC 的 Bluetooth 名稱，讓 iPhone 與 PC 配對。
- 疑難排解要求檢查 Device Manager 中的 Bluetooth hardware 與 driver。
- Mac 流程也要求 iPhone 先搜尋 Mac，再由兩端確認 pairing。
- 進入地圖頁後，官方要求短暫關閉再開啟 Location Services、Cellular 與 Wi-Fi。

這些操作是「iPhone 與電腦建立實際 Bluetooth pairing」的可信證據。Tenorshare 的版本紀錄顯示 4.6.3 加入 Bluetooth connection mode、4.7.2 加入 direct connection mode，4.10.0 加入 iOS 26 相容性。[Tenorshare 技術規格與版本紀錄](https://www.tenorshare.com/tech-spec/ianygo-location-changer.html)

同一篇官方文章聲稱 Game Mode 不再依賴 Apple developer platform，但沒有公開支撐該說法的 profile、service UUID、MFi 宣告、封包或 Core Location log。本文因此只把它當作 Tenorshare 對自家產品架構的主張，不把它當作可重作協定或來源旗標的證據。

### iAnyGo iOS App／Assistant

這是另一套方案，不應拿來證明 Desktop Bluetooth Game Mode 的機制。官方指南顯示：

- TestFlight 路徑會設定 VPN、安裝 trust/resource files 並等待 iOS components。
- iOS 14–16.7 的一條流程要求 Developer Mode；iOS 17.2+ 的 TestFlight 段落未列 Developer Mode。
- Assistant 路徑會安裝 IPLocate，並請使用者允許新增 VPN configuration。
- 官方標示 iOS App 支援 iOS 14–26，但排除 iOS 17.0／17.1。

這足以確認 companion app、VPN 與電腦初始化是某些 iAnyGo 產品路徑的一部分；不能把這些需求套用到 Bluetooth Game Mode，也不能反向聲稱 Bluetooth Game Mode 一定不使用任何首次 USB 初始化。

## iOS 17、18、26 與 Developer Mode

| 版本／路徑 | 官方公開狀態 |
| --- | --- |
| iOS 17 Desktop | Tenorshare 技術規格列為支援；一般 USB／Wi-Fi 指南未逐版列 Developer Mode 要求。 |
| iOS 18 Desktop Bluetooth | Bluetooth 指南明列 iOS 18 的 Bluetooth 連線操作，未列 iOS App、VPN、profile 或 Developer Mode 為 Game Mode 前置條件。 |
| iOS 26 Desktop | 技術規格與一般指南列為支援；Bluetooth 指南以「iOS 18 and above」描述較新版本操作，但沒有提供 iOS 26 的來源旗標測量。 |
| iOS App | 官方指南標示支援到 iOS 26、排除 17.0／17.1，且不同 TestFlight／Assistant 流程具有不同的 VPN、trust files、components 與 Developer Mode 步驟。 |

Apple 對 Developer Mode 的官方定義是允許開發簽名 App、Xcode 執行與其他 developer-only 功能；它本身不是 external accessory 的證明。[Apple：Enabling Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)

## 官方安裝檔的唯讀靜態觀察

2026-08-18 從 Tenorshare 官方下載網址取得的 Windows installer：

- URL：<https://download.tenorshare.com/downloads/ianygo_2573.exe>
- `ProductVersion`：`4.11.11`
- 大小：`297,924,064` bytes
- SHA-256：`6D2C725DF96C0C6A545F898A1732399D53D6FB8C5663495C05888CCA4A4725DC`
- Authenticode：Windows 驗證為有效；簽署者為 `AFIRSTSOFT CO., LIMITED`。

未執行安裝程式；只列出 Inno Setup 內容並檢查 PE import／export 名稱。可觀察到：

- Apple Mobile Device／USB 元件、`iOSRsdRemoteDevice.dll`、Apple VID 的自訂 USB NCM driver，以及 Developer Mode 教學資源。
- 主程式匯入的 device-management API 同時包含 iOS 17 remote-device／trust／driver 流程，以及 `BluetoothConnected`、`BluetoothMatch`、`BluetoothAuthorization`、`BluetoothCertifie` 等獨立狀態。
- 套件另含 `liblib_pogo_client.dll`，其網路 import 包含 Winsock。

這支持「同一產品同時包含 USB developer-device plumbing 與另外一套 Bluetooth Game Mode」的判斷，也符合官方將 General Mode 與 Game Mode 分開的 UI 流程。它**沒有**揭露可驗證的 GNSS／MFi protocol；而且二進位可能被封裝或保護，所以未在檔名與 import 名稱看到 NMEA、iAP2 或 ExternalAccessory，也不能當成不存在這些機制的證明。

## 兩個 Core Location 旗標能證明什麼

Apple 對兩個值的定義是彼此獨立的：

- [`isProducedByAccessory`](https://developer.apple.com/documentation/corelocation/cllocationsourceinformation/isproducedbyaccessory)：Core Location 從連接至裝置的 external accessory 取得位置時為 `true`；Apple 的例子是 Made for iPhone GPS dongle 或 CarPlay。
- [`isSimulatedBySoftware`](https://developer.apple.com/documentation/corelocation/cllocationsourceinformation/issimulatedbysoftware)：系統以 on-device software simulation 產生位置時為 `true`；Apple 以 Xcode debugger 載入 GPX 為例。

所以「第三方工具送入的座標沒有被標成 software simulation」不會自動推出「它是 accessory」。反過來，原生 Pokémon GO、Apple Maps 或其他 App 顯示修改後座標，也只證明系統或 App 收到了位置，不能推出 `isProducedByAccessory == true`。

截至本次調查，Tenorshare 官網沒有公開 `CLLocationSourceInformation`、`isProducedByAccessory`、`isSimulatedBySoftware`、原始 `CLLocationManager` callback 或 sourceInformation 為 `nil` 與否的測量。因此 iAnyGo 目前不是本規格驗收條件的反例。

## MFi 判斷

Apple 的公開 Bluetooth profile 清單列出 WiAP 並說它用於 MFi-certified accessories，但沒有列出一般 GNSS／NMEA／SPP profile。[Apple：iOS／iPadOS 支援的 Bluetooth profiles](https://support.apple.com/en-us/102842)

更直接的是 Apple Platform Security：經驗證的 MFi accessory 才能要求額外 transport 與功能，Apple 舉的功能例子包含「透過 Bluetooth 提供 location information」，並說 authentication IC 用來限制只有核准 accessory 能取得完整存取。[Apple：Verifying accessories](https://support.apple.com/guide/security/verifying-accessories-sec70a4f377d/web)

由此可以下兩個不同層級的結論：

1. **Apple 公開、受支援的路徑**：外接配件經 Bluetooth 提供系統定位，公開文件明確指向 MFi 驗證。
2. **iAnyGo 的產品事實**：終端使用者可以利用 PC 現有 Bluetooth adapter，不另買 MFi bridge；但 Tenorshare 沒有公開它如何跨過上述平台邊界。

兩者並不矛盾。iAnyGo 可能使用授權元件、私有協定或未公開實作，也可能根本沒有產生 accessory flag；公開資料無法在這些可能性中做選擇。本專案又明確排除破解私有協定與繞過 MFi，因此不能因為 iAnyGo 可用就直接把它當作可實作設計。

## 下一個最小黑箱實驗

在採購任何 bridge 前，先用現有 iPhone、iAnyGo 試用版與本專案的 iOS Source Probe 完成約半天至一天的黑箱測試。不要擷取或逆向私有 payload。

### 測試矩陣

使用同一台實體 iPhone、同一個座標與同一個 Source Probe build，依序測：

1. 真實定位 baseline。
2. Sky Walker 現有 USB DVT Location Override。
3. iAnyGo Desktop General Mode。
4. iAnyGo Desktop Bluetooth Game Mode。

每個 callback 原樣記錄：

- iOS build、iAnyGo 版本、Windows Bluetooth adapter 與 driver 版本。
- timestamp、latitude、longitude、altitude、horizontal/vertical accuracy、speed、course。
- `sourceInformation == nil`。
- `isSimulatedBySoftware`。
- `isProducedByAccessory`。
- 當下 USB 是否已拔除、Developer Mode 是否啟用、Windows 與 iPhone 顯示的 Bluetooth pairing／connection 狀態。

Bluetooth case 必須在完成必要初始化後拔除 USB，確認位置更新仍會持續，避免把同時存在的 developer USB session 誤判為 Bluetooth 結果。Probe 只能記錄 `CLLocationManager` callback 傳入的原始 `CLLocation`，不能自行建構 `CLLocationSourceInformation`。

### 判讀

| iAnyGo Game Mode 結果 | 對本專案的意義 |
| --- | --- |
| `isProducedByAccessory == true` | 證明「無外接盒子的商用實作」可產生目標旗標；接著需向 Tenorshare／Apple 確認可授權、公開或 MFi 合規的實作途徑。未確認前仍不能重作私有協定。 |
| `isProducedByAccessory == false`，`isSimulatedBySoftware == true` | iAnyGo 不是本規格所需的 accessory baseline，MFi bridge 主線不受影響。 |
| 兩者皆 `false` 或 `sourceInformation == nil` | iAnyGo 雖能改位置，仍未滿足規格；同時證明兩旗標不是完備的 spoofing taxonomy。 |
| 結果不穩定／隨 iOS 版本改變 | 把來源旗標當成逐 iOS build 的相容性驗收，不應從單一版本推廣。 |

如果後續 iAnyGo 基準在第一台 iPhone 上得到 `isProducedByAccessory == true`，再補 iOS 18 與 iOS 26 各一台的重測，以及只讀的 Bluetooth service/profile enumeration。未確認公開、可授權或 MFi 合規的途徑前，仍不得重作私有協定；若始終找不到合規路徑，才進入 Bad Elf 類 MFi Simulation Bridge 的詢價／借測與 adapter 實作。

## 對目前計畫的建議調整

- 暫停採購 MFi Simulation Bridge；它是 fallback，不再是假設為唯一可行的第一步。
- 保留 Bluetooth peripheral 邊界與獨立 iOS Source Probe。
- 依 ADR-0004，先以三次 120 秒 session 證偽 BLE LNS；未通過後才做 iAnyGo 黑箱來源旗標與使用者指定安裝目錄的唯讀調查。
- 不因 iAnyGo 的行銷描述放寬「不破解私有協定、不繞過 MFi」的範圍。
- 在黑箱實測前，規格文件應寫成「Apple 公開路徑預期需要 MFi；是否存在不需額外硬體且符合來源旗標的可授權路徑，待 iAnyGo benchmark 驗證」，而不是「已確認必須購買 bridge」。
