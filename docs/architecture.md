> 2026-09-19 玩法更新：預設已改為 GPS 固定面積方格、首次進入永久點亮、每六個新格觸發事件。本文原有 H3／停留計分敘述及既有驗收數字屬舊版；現行機制與限制見 [新版說明](劇情生成與物件機制說明.md)。

# 實作架構與世界不變量

## 資料路徑

Android `LocationManager` → OkHttp WebSocket → 板端 bounded EventBus → GPS validator → raw + filtered geofence → H3 → exploration → scene mapper → SQLite transaction → SDL UI。

`World` 是唯一世界寫入者。GPS thread、vision thread、audio/ASR thread 只提交 typed message；UI/main thread 排出事件並操作 SQLite。LLM worker 只能傳回文字；按下 Talk 的原始 cell、canonical dialogue 已變更時丟棄過期文字。

## 核心不變量

- 每格事件由 `events.cell_id UNIQUE` 保證唯一，事件／NPC／quest／map EXPLORED 同 transaction。
- world seed、H3 resolution、schema version 持久化；以不同 seed/resolution 開既有 DB 會拒絕啟動，避免悄悄重建世界。
- reboot 保留探索 component、觀察 thumbnail、事件、玩家、背包、NPC memory、任務與旗標。不將離線經過時間當作停留時間。
- GPS timestamp 單調增加；過舊、未來、NaN、範圍外與 teleport 會拒絕。低精度及快速移動只顯示、不累積。
- 只累積相鄰且有效、同 cell、間隔短的 GPS samples。以濾波軌跡與 noise floor 排除小抖動。此為 GPS heuristic，真實裝置仍需校準；不保證消除所有 GNSS 多路徑誤差。
- allowlist 空集合 fail closed。Polygon/MultiPolygon 支援 holes。禁入點不能因 smoothing 移到圍欄內而獲准。`BLOCKED` 是目前不安全點的 cell 記錄，不會永久封鎖整個與禁區部分重疊的 H3 cell。
- 每個 observation 都有 capture timestamp、cell、indoor probability、confidence 與 16×8 grayscale thumbnail；重複或差異不足不加分。原始影像不儲存。
- 沒有當前新鮮 scene，或室內概率過高，達探索門檻也等待，不自動發事件。
- 已探索格可顯示既有事件並手動互動；永遠不再經由探索生成 NPC／quest／event。
- Seed 用 SHA-256(world_seed:cell_id) 初始化，避開 Python randomized hash，跨 restart 穩定。Environment 改變事件分布，不直接修改世界。
- 戰鬥、資源、任務獎勵均由規則交易修改；重複按鈕不重複領取。

## 失效與資源

- 核心 runtime 不發 Internet request；地圖只讀 SQLite MBTiles，無在線 fallback。
- 視覺／語音／LLM inference 共享 lock，避免同時推論。Vision 固定單 camera buffer、短 burst，已知區域 idle。
- LLM 使用限時子程序，用完即卸載，低 RAM 不啟動。CLI failure／timeout／不合規輸出使用 template。
- ASR 是可選 CLI，ALSA 捕捉或 model 失敗不會關掉 UI。音訊只在暫存 WAV 中解碼，之後刪除。
- UI 顯示 process RSS、可用 RAM、CPU、GPS rate、vision runtime、camera FPS、ASR／LLM latency、DB duration。vision runtime 含整個 TFLite invoke，**不能當作 NPU-only 計時**。
- 真機必須測量含子程序的總 RAM；主 UI RSS 不包含 ASR／LLM child RSS。

## 範圍限制

Python MVP 不包含 C++ rewrite、模型訓練、任意 TFLite detector 自動辨識、vector MBTiles、室內定位或導航。視覺介面目前支援 NHWC RGB classifier + SSD-style detector。場域圍欄與地圖由部署者提供。手機使用前景 Activity，切到背景即停止送位置，板端凍結探索；不宣稱提供背景定位 service。
