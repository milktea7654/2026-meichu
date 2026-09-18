> 2026-09-19 玩法更新：預設已改為 GPS 固定面積方格、首次進入永久點亮、每六個新格觸發事件。本文原有 H3／停留計分敘述及既有驗收數字屬舊版；現行機制與限制見 [新版說明](劇情生成與物件機制說明.md)。

# 規格驗收追蹤

狀態：**可運行 host MVP；FRDM v1.0 尚未完成硬體驗收。**

`spec.md` 是需求來源。本表不修改或放寬原本 DoD。2026-09-18 的工作環境為 x86_64 WSL，沒有 FRDM SSH／相機／麥克風／NPU／模型／真實場域資料。

| Phase | 已交付 | 尚需實際驗收 |
|---|---|---|
| 0 Board | 程式入口、SQLite、bringup script、部署 service 範本 | 板子 boot、Wi-Fi、HDMI、camera、ALSA 各介面 |
| 1 GPS | Android 原始碼與 debug APK、前景 GNSS、重連、board WebSocket、validation；loopback 通過 | 手機安裝與真機走動 |
| 2 Map | H3、raster MBTiles TMS、Fog、玩家／accuracy／quest／event／blocked overlays、缺 tiles grid | 場域 MBTiles、HDMI 顯示／GPS 移動 |
| 3 Exploration | 四態、component score、安全圍欄、SQLite、重入不重複、restart tests | 實際圈定戶外 geofence、走動與 power-cycle |
| 4 Vision | V4L2 burst worker、量化 TFLite classifier/SSD decoder、Ethos-U delegate interface、去重 | 場景／物件模型、Vela compile、NPU 推論與場景準確率 |
| 5 Events | reality mapper、seeded selection、八類 event、transaction persistence、event log | 相機真實場景如何改變分布 |
| 6 RPG | 玩家、道具、NPC facts、quest、flags、簡化 combat；完整任務測試 | 板子按鈕實際完整流程 |
| 7 Voice | ALSA energy VAD、local CLI ASR adapter、intent parser、UI fallback | 本地聲學模型與 ARM64 latency／六命令可靠性 |
| 8 LLM | template、限時 local llama CLI、RAM guard、invalid/timeout fallback | 可選 GGUF 的 ARM64 記憶體／語言品質；MVP 可停用 |

## Mandatory tests

`tests/test_integration.py` 對應 T01–T15。T11／T12／T13 包含模擬故障，不能當作真實硬體 driver 穩定性證據。T15 禁止核心的 network connect／DNS；另有 loopback GPS transport 測試。完整 Internet 拔線仍需板端實測。新增精確圍欄線段交點判定與無效 SceneObservation 隔離測試；主機完整回歸共 66 項通過（2026-09-19，含瀏覽器模擬器後端）；瀏覽器任務、SQLite 檢視、劇情說明與重新載入另有 smoke test 通過。

另涵蓋 duplicate frames、GPS jitter、packet invalid、allowlist empty、event transaction rollback、quest reward idempotence；`test_network_map_ui.py` 驗證真 socket、拒絕非 GPS message、token、圖磚 TMS 與 UI click。

## v1.0 acceptance（對應 spec §40）

- 1–5：板端所有核心與 phone-only architecture 已交付；實體板獨立運行／Wi-Fi／無 PC 待驗。
- 6–11：position/H3/Fog/threshold/unique event host tests 通過；真實底圖與走動待驗。
- 12：vision pipeline 和 scene context 介面完成；camera/model/NPU 未驗。
- 13–14：SQLite event/quest/player 持久化、restart tests 通過；斷電待驗。
- 15–16：geofence、indoor guard tests 通過；實際場域與模型 false negative 待驗。
- 17–23：event history、NPC、quest、inventory、combat、2D UI、按鈕已實作，host smoke 通過。
- 24–25：voice/LLM 可停用、failure fallback tests 通過；實體聲學與 GGUF效能待驗。

## 完成硬體驗收需要的輸入

FRDM SSH 位址與可用帳號、BSP version、相機／麥克風 device、測試區域 allowed/blocked GeoJSON 與 raster MBTiles、兩個相容 quantized vision models 及 label/preprocessing。若要驗 enhancement，另提供本地 speech model 與 GGUF。

## 2026-09-19 模擬器交付與阻礙複核

繁體中文瀏覽器 UI、SQLite 唯讀檢視與劇情生成說明已交付，並確認本機 8787 服務可讀回旅人事件與 AVAILABLE 任務。模擬資料不取代 FRDM／手機戶外測試。再次檢查環境仍為 x86_64，沒有 camera、ALSA、Ethos-U 裝置，models 與正式 map 目錄為空，正式 geofence 沒有 feature。原規格仍受真機／場域／模型條件阻擋，未標記完成。
