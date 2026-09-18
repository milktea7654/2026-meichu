# FRDM-i.MX93 Outdoor Edge AI Exploration RPG

## Complete Implementation Specification — v1.0

---

# 0. Astra 執行指令

請依本文件實作一個 **FRDM-i.MX93 為主要運算核心的完全本地 Outdoor Exploration RPG**。

核心原則：

1. FRDM-i.MX93 是主系統，不是 peripheral。
2. 手機只負責取得 GPS/GNSS 位置，並透過 Wi-Fi 傳給 FRDM-i.MX93。
3. 手機不得負責：

   * 遊戲邏輯
   * 地圖探索判定
   * AI Vision
   * NPC AI
   * 世界狀態
   * 事件生成
4. Camera、Microphone、Vision、Voice、Map、World State、Event Engine、NPC、2D UI 全部運行在 FRDM-i.MX93。
5. 第一版只支援戶外探索。
6. 不做大型 VLM。
7. 不做 3D rendering。
8. 不依賴 Cloud AI。
9. 不要求完全自由 NPC 對話。
10. 小型文字模型為 enhancement，不得成為核心遊戲邏輯 dependency。
11. 已探索區域不得因玩家再次進入而自動產生新的事件或新劇情。
12. 只有「安全、有效、未探索」區域累積到探索門檻後才能觸發新事件。
13. 所有世界狀態必須持久化，reboot 後不得遺失。
14. 優先完成可執行 MVP，再加入 ASR、小型 LLM 等 enhancement。
15. 不要自行加入大型新功能，除非是完成本 spec 必須的依賴。

---

# 1. 專案目標

建立一個：

> Reality-Grounded、GPS-driven、Camera-aware、Offline Edge RPG。

玩家攜帶 FRDM-i.MX93 裝置在戶外移動。

手機提供 GPS 座標。

FRDM-i.MX93 根據玩家真實位置：

* 顯示現實世界 2D 地圖。
* 記錄玩家走過的區域。
* 建立 Fog of War。
* 判斷已探索與未探索區域。
* 在未探索區域累積探索度。
* 利用 Camera 分析當地環境。
* 將現實環境轉換為 RPG semantic context。
* 達到探索門檻後觸發 RPG event。
* 建立 NPC、Quest、Item、Combat 等遊戲狀態。
* 保存事件紀錄。
* 支援簡單語音命令。
* 支援有限度 NPC 文字/語音對話。
* 使用簡單 2D UI 顯示整個遊戲。

所有核心功能都應在 FRDM-i.MX93 本地完成。

---

# 2. 系統總架構

```text
                        ┌─────────────────────────┐
                        │       Smartphone        │
                        │                         │
                        │ GPS / GNSS              │
                        │ Lat / Lon               │
                        │ Accuracy                │
                        │ Speed                   │
                        │ Heading                 │
                        │ Timestamp               │
                        └────────────┬────────────┘
                                     │
                                  Wi-Fi
                              WebSocket/HTTP
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────┐
│                      FRDM-i.MX93                             │
│                                                              │
│                     Linux / Yocto                            │
│                                                              │
│  ┌────────────────┐     ┌───────────────────┐                │
│  │ Camera Input   │     │ Microphone Input  │                │
│  │ V4L2           │     │ ALSA              │                │
│  └───────┬────────┘     └─────────┬─────────┘                │
│          │                        │                          │
│          ▼                        ▼                          │
│  ┌────────────────┐     ┌───────────────────┐                │
│  │ Edge Vision    │     │ Voice Pipeline    │                │
│  │ Ethos-U65 NPU  │     │ VAD / ASR / KWS   │                │
│  └───────┬────────┘     └─────────┬─────────┘                │
│          │                        │                          │
│          ▼                        │                          │
│  SceneObservation                │ Player Intent             │
│          │                        │                          │
│          └─────────────┬──────────┘                          │
│                        ▼                                     │
│             ┌───────────────────────┐                        │
│             │ Location / Exploration│                        │
│             │ Engine                │                        │
│             │                       │                        │
│             │ H3                    │                        │
│             │ Fog of War            │                        │
│             │ Exploration Progress  │                        │
│             │ Geofence              │                        │
│             └───────────┬───────────┘                        │
│                         ▼                                    │
│             ┌───────────────────────┐                        │
│             │ Reality → RPG Mapper  │                        │
│             └───────────┬───────────┘                        │
│                         ▼                                    │
│             ┌───────────────────────┐                        │
│             │ RPG World Core        │                        │
│             │                       │                        │
│             │ Event Engine          │                        │
│             │ Quest Engine          │                        │
│             │ NPC State             │                        │
│             │ Inventory             │                        │
│             │ Rules / Combat        │                        │
│             └───────────┬───────────┘                        │
│                         │                                    │
│              ┌──────────┴──────────┐                         │
│              ▼                     ▼                         │
│      ┌───────────────┐      ┌───────────────┐                │
│      │ SQLite DB     │      │ Small LLM     │                │
│      │ Persistent    │      │ Optional      │                │
│      │ World State   │      │ NPC wording   │                │
│      └───────────────┘      └───────────────┘                │
│                         │                                    │
│                         ▼                                    │
│                ┌──────────────────┐                          │
│                │ 2D Map/UI Engine │                          │
│                │                  │                          │
│                │ Map              │                          │
│                │ Event Log        │                          │
│                │ Dialogue         │                          │
│                │ Inventory        │                          │
│                │ Quest            │                          │
│                └──────────────────┘                          │
└──────────────────────────────────────────────────────────────┘
```

---

# 3. Hardware Baseline

Target：

**NXP FRDM-i.MX93**

Hardware baseline：

* Dual Cortex-A55 @ 1.7 GHz
* Cortex-M33 @ 250 MHz
* Ethos-U65 NPU
* i.MX93 NPU configuration: 0.5 TOPS
* 2 GB LPDDR4/LPDDR4X RAM
* 32 GB eMMC
* MicroSD
* IW612 Wi-Fi 6
* MIPI CSI Camera interface
* USB
* HDMI display output
* Audio / expansion support

FRDM-i.MX93 為整個 application host。

Vision 優先 NPU。

遊戲與 world logic 使用 Cortex-A55。

Cortex-M33 第一版不強制使用。

---

# 4. Resource Budget

因為 RAM 只有 2 GB，所以不得同時常駐大量 AI model。

目標：

```text
OS + system:
< 500 MB

Game + UI + DB:
< 250 MB

Vision:
< 150 MB

ASR:
< 350 MB

Small LLM:
< 500 MB model/runtime target

Free/headroom:
>= 200 MB
```

這是 target，不是精確硬限制。

必須在真機 profile。

重要：

**Vision、ASR、LLM 不應全部持續處於 active inference。**

使用事件式 activation。

---

# 5. Operating System

第一選擇：

```text
NXP Yocto Linux BSP
```

Architecture：

```text
aarch64
```

開發期間允許使用 Python prototype。

Performance critical component 優先：

```text
C++17/C++20
```

最終 runtime 不應依賴 desktop PC。

---

# 6. Repository Layout

建議：

```text
project/
│
├── apps/
│   ├── board_app/
│   └── android_gps_bridge/
│
├── src/
│   ├── core/
│   ├── network/
│   ├── location/
│   ├── exploration/
│   ├── safety/
│   ├── camera/
│   ├── vision/
│   ├── audio/
│   ├── asr/
│   ├── intent/
│   ├── world/
│   ├── events/
│   ├── quests/
│   ├── npc/
│   ├── dialogue/
│   ├── map/
│   ├── ui/
│   ├── storage/
│   └── common/
│
├── models/
│   ├── vision/
│   ├── speech/
│   └── text/
│
├── assets/
│   ├── map/
│   ├── npc/
│   ├── icons/
│   ├── dialogue/
│   └── events/
│
├── config/
│   ├── game.yaml
│   ├── exploration.yaml
│   ├── safety.yaml
│   └── models.yaml
│
├── data/
│   ├── allowed_areas.geojson
│   ├── blocked_areas.geojson
│   └── world.db
│
├── tests/
│
├── scripts/
│
├── docs/
│
└── CMakeLists.txt
```

---

# 7. 手機 GPS Bridge

## 7.1 Responsibility

手機只負責：

```text
GPS/GNSS sensor
+
Wi-Fi bridge
```

禁止將 game logic 移到手機。

---

# 7.2 Network

第一版：

```text
Phone Hotspot
       ↓
FRDM Wi-Fi client
```

FRDM 建立 WebSocket server。

建議：

```text
ws://BOARD_IP:8765/location
```

手機每：

```text
500 ms ～ 1 s
```

傳送一次位置。

---

# 7.3 GPS Packet

```json
{
  "type": "location",
  "latitude": 24.123456,
  "longitude": 120.123456,
  "accuracy_m": 4.8,
  "speed_mps": 1.1,
  "heading_deg": 82.0,
  "timestamp_ms": 1789651220000
}
```

必要：

* latitude
* longitude
* accuracy
* timestamp

可選：

* speed
* heading
* altitude

---

# 7.4 GPS Validation

FRDM 收到 packet 後：

```text
packet received
      ↓
timestamp valid?
      ↓
accuracy valid?
      ↓
speed valid?
      ↓
outlier rejection
      ↓
position smoothing
      ↓
accepted position
```

預設：

```text
accuracy <= 15 m
→ 可累積探索度

15 < accuracy <= 25 m
→ 顯示位置
→ 不累積探索度

accuracy > 25 m
→ GPS_INVALID
```

若：

```text
speed > 2.5 m/s
```

第一版停止探索度累積，避免搭車刷地圖。

參數全部 configurable。

---

# 7.5 Disconnect

5 秒沒有 location packet：

```text
GPS_STALE
```

行為：

* 保留最後顯示位置。
* 停止 exploration progress。
* 禁止觸發新事件。
* UI 顯示 GPS connection warning。

---

# 8. Spatial Grid

使用：

```text
Uber H3
```

MVP 預設：

```text
H3 resolution = 11
```

H3 官方統計中 resolution 11 平均 hex edge 約 28.7 m；resolution 12 約 10.8 m。第一版用 res 11 是為了降低手機 GPS 飄移造成的 cell jumping。

必須可以透過 config：

```yaml
h3_resolution: 11
```

調整。

---

# 9. Cell State

每個 H3 cell：

```text
UNSEEN
DISCOVERING
EXPLORED
BLOCKED
```

資料：

```json
{
  "cell_id": "8b28308280f4fff",
  "state": "DISCOVERING",
  "progress": 0.57,
  "first_entered_at": 1789651000,
  "last_seen_at": 1789651250,
  "event_triggered": false,
  "event_id": null,
  "blocked": false
}
```

---

# 10. Exploration Rules

這是遊戲最重要的 state machine。

```text
ENTER CELL
   │
   ▼
BLOCKED?
   │
   ├── YES → STOP
   │
   ▼
EXPLORED?
   │
   ├── YES
   │      ↓
   │  Show existing map state
   │  NO new story/event
   │
   ▼
UNSEEN
   │
   ▼
DISCOVERING
   │
   ▼
Accumulate exploration progress
   │
   ▼
progress >= threshold?
   │
   ├── NO → continue
   │
   └── YES
           ↓
      ANALYZE SCENE
           ↓
       EVENT CREATE
           ↓
       SAVE WORLD
           ↓
        EXPLORED
```

---

# 11. Exploration Progress

MVP 計算：

```text
progress =
0.35 × dwell_score
+
0.35 × movement_score
+
0.20 × observation_score
+
0.10 × landmark_score
```

全部 component：

```text
0.0 ～ 1.0
```

---

## 11.1 Dwell Score

```text
dwell_score =
min(valid_time_in_cell / 30 sec, 1)
```

---

## 11.2 Movement Score

計算玩家在 cell 內有效移動。

例如：

```text
movement_score =
min(distance_walked_inside_cell / 25 m, 1)
```

GPS jitter 不得計算。

必須使用 filtered trajectory。

---

## 11.3 Observation Score

Camera 分析期間不同有效 observation 累積。

例如：

```text
0 observations = 0
1 = 0.25
2 = 0.50
3 = 0.75
>=4 = 1.0
```

必須使用 sufficiently-different frames。

禁止同一畫面重複刷分。

---

## 11.4 Landmark Score

若 Vision confidence 足夠找到：

* bridge
* pond
* statue
* large building
* plaza
* trail junction
* landmark-like structure

則：

```text
landmark_score = 1
```

否則：

```text
0
```

---

## 11.5 Trigger Threshold

預設：

```text
EVENT_TRIGGER_THRESHOLD = 0.70
```

configurable。

---

# 12. 已探索區域規則

這是硬規則。

若：

```text
cell.state == EXPLORED
```

玩家重新進入：

禁止：

* 自動生成新事件。
* 自動生成新劇情。
* 自動生成新 NPC。
* 自動新增 quest。

允許：

* 顯示原有地圖。
* 查看已發生事件。
* 查看既有地標。
* 查看既有 NPC。
* 手動繼續已建立 quest。
* 手動與既有 NPC 互動。

這些不算「探索觸發」。

---

# 13. Outdoor Safety / Geofence

第一版：

**Outdoor only**

原因：

* 室內手機 GNSS 不可靠。
* 無法辨認樓層。
* 不希望遊戲引導玩家進入私人、危險或禁止區域。

---

# 13.1 Allowed Area

使用：

```text
allowed_areas.geojson
```

定義可探索 polygon。

例如：

* 校園公共戶外空間。
* 公園。
* 公共步道。
* 公開道路旁安全空間。

---

# 13.2 Blocked Area

```text
blocked_areas.geojson
```

包括：

* 建築 footprint。
* 私人區域。
* 危險道路。
* 水域。
* 工地。
* 禁止區域。

---

# 13.3 Hard Rule

如果：

```text
!inside_allowed_area
OR
inside_blocked_area
OR
gps_invalid
```

則：

```text
exploration_progress = frozen
event_trigger = disabled
```

UI 顯示：

```text
目前區域不可探索
```

禁止遊戲提示：

```text
「進入建築」
「跨越圍欄」
「走進水域」
```

等會讓玩家離開合法、安全路徑的指令。

---

# 13.4 Indoor Vision Guard

Camera Scene Classifier 可以提供：

```text
INDOOR confidence
```

若：

```text
indoor_probability > configured threshold
```

則禁止觸發 exploration event。

此項只做 secondary guard。

主要限制仍使用地圖 geofence。

---

# 14. Camera Pipeline

Camera abstraction：

```text
V4L2
```

如果 USB camera：

```text
/dev/videoX
```

---

# 14.1 Camera Behavior

不要永久高 FPS inference。

狀態：

```text
KNOWN CELL
→ camera low-rate / idle

NEW DISCOVERING CELL
→ wake

EVENT SCENE ANALYSIS
→ burst capture
```

預設：

```text
1–2 inference frames/sec
```

連續：

```text
5–10 sec
```

建立 scene observation。

---

# 15. Edge Vision

Target：

```text
Ethos-U65
```

模型必須優先採用可被 Ethos-U/Vela 編譯的量化模型。

Ethos-U65 適合 8-bit neural-network inference；不要把大型 Transformer/VLM 設計成 NPU dependency。Arm 對原生 Transformer support 是在較新的 U85 特別列出的能力。

---

# 15.1 Vision Tasks

MVP 只做：

### Scene Classification

classes，例如：

```text
park
road
campus
plaza
trail
forest_like
riverside
lake_side
urban_outdoor
unknown
indoor
```

### Object Detection

第一版控制在約：

```text
15–30 classes
```

例如：

```text
tree
bench
building
bridge
statue
sign
pond
river
stairs
path
road
bicycle
vehicle
person
fence
gate
shopfront
```

不要第一版做 hundreds classes。

---

# 15.2 Optional Segmentation

Semantic segmentation：

**P1 optional**

不是 MVP blocker。

先完成：

```text
scene classification
+
object detection
```

---

# 15.3 SceneObservation

Vision 不直接創造 RPG。

輸出客觀 observation：

```json
{
  "timestamp": 1789651234,
  "scene": "park",
  "scene_confidence": 0.91,
  "objects": [
    {
      "class": "tree",
      "confidence": 0.92
    },
    {
      "class": "pond",
      "confidence": 0.87
    },
    {
      "class": "bench",
      "confidence": 0.81
    }
  ],
  "indoor_probability": 0.03
}
```

---

# 16. Reality → RPG Mapper

Vision 不得自己幻想。

Mapper 接收：

```text
SceneObservation
+
Location state
+
World state
```

輸出：

```text
RpgContext
```

---

# 16.1 Example

Reality：

```text
scene = park

objects:
tree
pond
bridge
bench
```

輸出：

```json
{
  "biome": "green_zone",
  "location_archetype": "forest_shrine",
  "event_tags": [
    "nature",
    "water",
    "mystery",
    "rest"
  ],
  "npc_bias": [
    "traveler",
    "herbalist"
  ],
  "encounter_bias": [
    "low_danger"
  ]
}
```

---

# 16.2 Mapping

不要：

```text
pond → 固定 monster
```

使用 weighted rules：

```text
pond:

water_event: 0.35
mystery:     0.25
npc:         0.20
resource:    0.15
rare:        0.05
```

隨機必須 seeded。

Seed：

```text
world_seed + cell_id
```

同一世界同一區域必須可重現。

---

# 17. RPG World Core

這是遊戲主控制器。

不得讓 LLM 成為 world state authority。

只有 World Core 可以修改遊戲狀態。

---

# 17.1 Modules

```text
WorldStateManager
ExplorationManager
EventEngine
QuestEngine
NpcManager
InventoryManager
CombatEngine
RuleEngine
SafetyManager
DialogueManager
```

---

# 18. Event Engine

事件輸入：

```text
cell
RpgContext
player state
quest state
world flags
```

輸出：

```text
GameEvent
```

---

# 18.1 Event Types

MVP：

```text
DISCOVERY
NPC_ENCOUNTER
RESOURCE
QUEST
COMBAT
LANDMARK
REST
RARE
```

---

# 18.2 Example

```json
{
  "event_id": "evt_A123_001",
  "cell_id": "8b283...",
  "type": "NPC_ENCOUNTER",
  "archetype": "injured_traveler",
  "status": "ACTIVE",
  "created_at": 1789651250
}
```

---

# 18.3 Event Guarantee

每 cell：

MVP 最多：

```text
1 exploration-triggered primary event
```

成功產生後：

```text
event_triggered = true
```

不得重複。

---

# 19. Quest System

Quest 必須為 deterministic structured state。

```json
{
  "quest_id": "quest_014",
  "state": "ACTIVE",
  "stage": 2,
  "objective": "find_lost_item",
  "target_cell": "...",
  "rewards": {
    "xp": 50
  }
}
```

Quest states：

```text
LOCKED
AVAILABLE
ACTIVE
COMPLETED
FAILED
```

LLM 不可直接修改 quest state。

---

# 20. NPC System

NPC：

```json
{
  "npc_id": "npc_032",
  "name": "神秘旅人",
  "archetype": "traveler",
  "cell_id": "...",
  "relationship": 0,
  "dialogue_state": "INTRO",
  "quest_id": "quest_014",
  "alive": true
}
```

NPC memory：

只保存 structured facts。

例如：

```json
{
  "player_helped": true,
  "player_threatened": false,
  "quest_completed": false
}
```

不要讓小型 LLM 自己記住所有歷史。

---

# 21. Small Local Text Model

目的：

**不是負責世界推理。**

只負責：

* NPC wording。
* 1–3 句短對話。
* 將 structured event 改寫成自然文字。
* 有限的玩家 intent parsing。

---

# 21.1 Runtime

建議 abstraction：

```text
DialogueBackend
```

implementation：

```text
TemplateDialogueBackend
LlamaCppDialogueBackend
```

第一版永遠保留 Template fallback。

---

# 21.2 Model Constraint

目標：

```text
~300M–600M class
GGUF
4-bit quantized
```

不要直接綁死單一 model。

透過：

```yaml
dialogue:
  backend: llama_cpp
  model: /models/text/model.gguf
  max_context: 1024
  max_output_tokens: 64
```

切換。

---

# 21.3 LLM Prompt

LLM 每次只能看到必要資料。

例如：

```text
SYSTEM:
你是一名 RPG NPC。
只能根據提供的 WORLD FACTS 回答。
不可創造新的地點、物品、任務或角色。
回答最多三句。

NPC:
Name: 神秘旅人
Mood: nervous

WORLD FACTS:
Location: riverside
Player has not accepted quest.
A broken bridge exists.

PLAYER:
你在這裡做什麼？
```

---

# 21.4 LLM Output

只輸出：

```text
dialogue text
```

禁止直接輸出 DB command。

禁止修改：

* Item
* Quest
* World flag
* NPC state

所有 state change 都由 RuleEngine 執行。

---

# 21.5 Fallback

如果：

* LLM load failure。
* inference timeout。
* memory pressure。
* invalid output。

立即：

```text
TemplateDialogueBackend
```

遊戲不得因 LLM failure crash。

---

# 22. Microphone / Voice

Camera 若提供 microphone，先透過 Linux ALSA 確認是否以音訊裝置暴露。

建立：

```text
AudioInput abstraction
```

不要把程式綁死某個 USB device id。

---

# 22.1 Audio Pipeline

```text
Microphone
   ↓
ALSA
   ↓
16 kHz mono PCM
   ↓
VAD
   ↓
Speech segment
   ↓
ASR/KWS
   ↓
Intent Parser
   ↓
Game Command
```

---

# 22.2 Voice Scope

第一版只需要：

```text
打開地圖
調查
交談
接受
拒絕
離開
查看任務
查看背包
```

以及簡短 NPC conversation。

---

# 22.3 ASR Candidate

優先評估：

```text
sherpa-onnx
```

因為目前支援：

* Linux ARM64
* offline ASR
* streaming ASR
* VAD
* keyword spotting

適合這種嵌入式 pipeline。

Alternative：

```text
whisper.cpp tiny
```

whisper.cpp 支援 ARM/Linux、CPU inference、quantization；其官方 README 列 tiny 約需 273 MB runtime memory，因此仍可能適合作為實驗 backend，但真機速度必須 benchmark。

不要讓 Whisper 成為 MVP prerequisite。

---

# 23. Intent Parser

ASR 輸出後不要直接交 LLM。

先做 deterministic parser。

例如：

```text
"我想跟他說話"
→ TALK

"調查這裡"
→ INSPECT

"我要離開"
→ LEAVE
```

使用：

* Exact command
* Keyword mapping
* Simple fuzzy matching

confidence 太低：

```text
UNKNOWN
```

UI 顯示可選按鈕 fallback。

---

# 24. Database

使用：

```text
SQLite
```

Single source of truth。

---

# 24.1 Tables

至少：

```text
world_meta
player
map_cells
scene_observations
events
event_log
quests
npcs
npc_memory
inventory
items
world_flags
settings
```

---

# 24.2 map_cells

```sql
CREATE TABLE map_cells (
    cell_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    first_entered_at INTEGER,
    last_seen_at INTEGER,
    event_triggered INTEGER NOT NULL DEFAULT 0,
    event_id TEXT,
    blocked INTEGER NOT NULL DEFAULT 0
);
```

---

# 24.3 events

```sql
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    cell_id TEXT NOT NULL,
    type TEXT NOT NULL,
    archetype TEXT,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    completed_at INTEGER,
    payload_json TEXT
);
```

---

# 24.4 event_log

```sql
CREATE TABLE event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    cell_id TEXT
);
```

---

# 25. Offline Map

第一版不要依賴 internet map API。

使用預先下載：

```text
MBTiles
```

底圖來源可使用 OpenStreetMap-compatible data。

測試區域先只包：

```text
校園 / 測試公園 / 指定區域
```

不要一開始放整個台灣高 zoom tiles。

---

# 26. Map UI

Target：

```text
1280 × 720
```

適合 FRDM HDMI demo。

第一版可使用：

```text
SDL2
+
SDL_ttf
+
MBTiles renderer
```

也可以用 Qt，如果 BSP 環境已經完整支援。

但不要為 UI 引入非常重的 browser runtime，除非實測 RAM 足夠。

---

# 26.1 UI Layout

```text
┌──────────────────────────────────────────────┐
│ MAP                                          │
│                                              │
│  ░░░░░░░  未探索                             │
│  ▓▓▓▓▓▓▓  已探索                             │
│                                              │
│                  ● YOU                       │
│        ? event                               │
│        ★ landmark                            │
│                                              │
├───────────────────────┬──────────────────────┤
│ Event Log             │ Current Interaction  │
│                       │                      │
│ 10:23 發現河邊步道     │ 神秘旅人：           │
│ 10:25 發現石橋         │ 「你終於來了。」      │
│ 10:28 觸發事件         │                      │
│                       │ [交談] [調查] [離開] │
└───────────────────────┴──────────────────────┘
```

---

# 26.2 Map Overlay

顯示：

* Player position
* GPS accuracy circle
* Explored cells
* Unexplored cells
* Landmark
* Existing event markers
* Quest marker
* Blocked zone

Fog of War：

```text
EXPLORED:
normal map

UNSEEN:
dark/gray overlay
```

---

# 27. Event Log

UI 顯示最近：

```text
10–20 entries
```

完整紀錄留 DB。

例如：

```text
[10:23] 進入新區域：河邊步道
[10:24] 探索度 34%
[10:25] 發現地標：石橋
[10:27] 探索度 72%
[10:27] 事件：神秘旅人
[10:29] 接受任務：失落的物品
```

---

# 28. Main Runtime State Machine

```text
BOOT
 │
 ▼
INIT_DB
 │
 ▼
INIT_UI
 │
 ▼
INIT_NETWORK
 │
 ▼
WAIT_FOR_PHONE_GPS
 │
 ▼
READY
 │
 ▼
VALIDATE_POSITION
 │
 ├── INVALID
 │      ↓
 │   GPS_WARNING
 │
 ▼
CHECK_GEOFENCE
 │
 ├── BLOCKED
 │      ↓
 │   SAFE_IDLE
 │
 ▼
RESOLVE_H3_CELL
 │
 ├── EXPLORED
 │      ↓
 │   KNOWN_AREA
 │      ↓
 │   NO NEW EVENT
 │
 └── NEW / DISCOVERING
        ↓
    START_EXPLORATION
        ↓
    CAMERA ANALYSIS
        ↓
    ACCUMULATE PROGRESS
        ↓
    THRESHOLD?
       │
       ├── NO → continue
       │
       └── YES
              ↓
          GENERATE RPG CONTEXT
              ↓
          CREATE EVENT
              ↓
          SAVE DATABASE
              ↓
          MARK EXPLORED
              ↓
          PLAYER INTERACTION
```

---

# 29. Internal Event Bus

模組不要互相任意 call。

建立 typed event：

```text
GpsUpdated
GpsInvalid
CellEntered
CellBlocked
ExplorationUpdated
SceneObserved
ExplorationThresholdReached
GameEventCreated
NpcInteractionStarted
VoiceIntentDetected
QuestUpdated
UiRefreshRequested
```

MVP 可使用：

```text
in-process observer/event queue
```

不需要第一版引入 Kafka/Redis 等外部系統。

---

# 30. Thread Model

建議：

```text
Main/UI thread

GPS network thread

Camera capture thread

Vision worker

Audio capture thread

ASR worker

World/DB thread
```

SQLite 盡量 single writer。

LLM worker：

```text
on demand
```

---

# 31. AI Activation Policy

## Normal Walking

```text
GPS      ON
UI       ON
Camera   idle / low frequency
Vision   idle
ASR      waiting/VAD
LLM      unloaded/idle
```

## New Area

```text
GPS      ON
Camera   ON
Vision   ON
LLM      OFF
```

## Event Dialogue

```text
Camera   idle
Vision   idle
ASR      ON
LLM      optional ON
```

不要同時把所有 AI workload 打滿。

---

# 32. Performance Safety

如果 memory：

```text
available RAM < configured threshold
```

優先：

1. unload LLM
2. reduce camera buffer
3. disable optional segmentation
4. fallback template dialogue

不得 kill core game process。

---

# 33. Data Privacy

預設：

* GPS 不送 cloud。
* Camera frame 不送 cloud。
* Microphone audio 不送 cloud。
* NPC text 不送 cloud。
* World database local only。

手機只與同一區域網路上的 FRDM 溝通。

---

# 34. Error Handling

## Camera unavailable

```text
exploration can continue
but event requiring environment analysis must wait
```

## Microphone unavailable

```text
UI buttons remain usable
```

## LLM unavailable

```text
template dialogue
```

## GPS unavailable

```text
freeze exploration
```

## Map tile missing

```text
render simple grid
do not crash
```

## Vision low confidence

使用：

```text
location_archetype = generic_outdoor
```

不要幻想具體現實物件。

---

# 35. Configuration

`config/game.yaml`

```yaml
world_seed: 12345

location:
  gps_valid_accuracy_m: 15
  gps_display_accuracy_m: 25
  max_exploration_speed_mps: 2.5

exploration:
  h3_resolution: 11
  event_threshold: 0.70
  dwell_target_sec: 30
  movement_target_m: 25

vision:
  enabled: true
  fps: 2
  analysis_duration_sec: 8

audio:
  enabled: true
  sample_rate: 16000

dialogue:
  llm_enabled: false
  max_output_tokens: 64

safety:
  outdoor_only: true
```

所有 tuning parameter 不得 hard-code。

---

# 36. MVP Implementation Order

Astra 必須照順序完成。

## Phase 0 — Board Bring-up

完成：

* Linux boot。
* Wi-Fi。
* HDMI。
* Camera capture。
* Microphone capture。
* SQLite。
* Basic executable。

DoD：

所有硬體介面 individually working。

---

## Phase 1 — Phone GPS Bridge

完成：

* Android minimal app。
* Phone GPS。
* Wi-Fi WebSocket。
* Board location receiver。
* reconnect。
* accuracy validation。

DoD：

走動時板端持續顯示正確 GPS packet。

---

## Phase 2 — Offline Map

完成：

* MBTiles load。
* player location。
* explored cell overlay。
* Fog of War。
* H3 conversion。

DoD：

玩家走動可以在地圖上移動。

---

## Phase 3 — Exploration Engine

完成：

* UNSEEN / DISCOVERING / EXPLORED / BLOCKED。
* exploration score。
* geofence。
* persistence。
* reboot recovery。

DoD：

未探索區達門檻變 EXPLORED。

已探索區永不重新自動觸發。

---

## Phase 4 — Vision

完成：

* camera burst。
* scene classifier。
* object detector。
* SceneObservation。
* NPU deployment。

DoD：

進新區時產生 structured SceneObservation。

---

## Phase 5 — RPG Mapping + Event Engine

完成：

* Reality→RPG mapper。
* seeded event selection。
* event creation。
* event persistence。
* event log。

DoD：

真實環境會改變事件 type bias。

---

## Phase 6 — RPG Core

完成：

* player。
* inventory。
* NPC state。
* quest。
* world flag。
* simplified combat/rule engine。

DoD：

至少可以完整跑一個：

```text
Explore
→ Event
→ NPC
→ Accept Quest
→ Item
→ Complete Quest
```

workflow。

---

## Phase 7 — Voice Command

完成：

* ALSA。
* VAD。
* command recognition。
* intent parser。
* button fallback。

DoD：

至少可靠辨識：

```text
調查
交談
接受
拒絕
離開
打開地圖
```

---

## Phase 8 — Small LLM

最後才加入。

完成：

* llama.cpp backend。
* small GGUF model。
* structured prompt。
* timeout。
* template fallback。

DoD：

NPC 可以根據 structured NPC state 回 1–3 句話。

LLM failure 不影響遊戲。

---

# 37. Mandatory Tests

至少建立以下 integration tests。

### T01 — GPS valid

有效 GPS：

```text
location updates
```

PASS。

### T02 — GPS inaccurate

```text
accuracy > threshold
```

不得累積探索。

### T03 — New cell

第一次進新 cell：

```text
UNSEEN → DISCOVERING
```

### T04 — Exploration threshold

progress：

```text
0.69
```

不得 event。

progress：

```text
>=0.70
```

只觸發一次。

### T05 — Re-enter explored cell

離開再回來：

不得產生第二個 exploration event。

### T06 — Reboot

reboot 後：

* explored cells 保留。
* event 保留。
* quest 保留。

### T07 — Blocked zone

blocked polygon：

不得增加 progress。

不得 event。

### T08 — Indoor

indoor guard：

不得 event。

### T09 — Phone disconnect

WebSocket lost：

停止 progress。

### T10 — GPS jump

異常 teleport：

reject。

### T11 — Vision failure

Vision unavailable：

不得 crash。

### T12 — LLM failure

LLM crash/timeout：

template fallback。

### T13 — Mic failure

UI interaction 正常。

### T14 — Event uniqueness

同一 cell：

不得重複建立 primary exploration event。

### T15 — Offline

完全移除 internet：

核心遊戲仍正常運作。

---

# 38. Logging

每個 subsystem：

```text
LOCATION
EXPLORE
VISION
AUDIO
ASR
WORLD
EVENT
QUEST
NPC
DB
UI
```

使用 structured logging。

例如：

```text
[LOCATION] accepted accuracy=4.8 cell=...
[EXPLORE] progress=0.63
[VISION] scene=park conf=0.91
[EVENT] triggered id=evt_013
[DB] transaction committed
```

---

# 39. Metrics

Debug build 顯示：

```text
RAM usage
CPU usage
NPU inference time
camera FPS
GPS update rate
ASR latency
LLM latency
DB transaction time
```

目的不是追求漂亮 benchmark。

目的是確定 2 GB RAM 不會 OOM。

---

# 40. Acceptance Criteria

v1.0 完成必須滿足：

1. FRDM-i.MX93 可以獨立運行遊戲。
2. 手機只提供 GPS。
3. 不需要 internet。
4. 不需要 PC。
5. GPS 可以透過 Wi-Fi 即時傳給板子。
6. 地圖顯示玩家真實位置。
7. 走過區域可以點亮。
8. 未探索區域會累積探索進度。
9. 未達探索門檻不得觸發事件。
10. 達門檻後可以觸發一次 RPG event。
11. 已探索區不得自動觸發新事件或劇情。
12. Camera 會影響 event context。
13. 世界狀態寫入 SQLite。
14. reboot 後世界保留。
15. 戶外 geofence 有效。
16. 室內/禁入區不觸發事件。
17. 有 event history。
18. 有簡單 NPC。
19. 有 quest。
20. 有 inventory。
21. 有簡單規則/戰鬥系統。
22. UI 完全 2D。
23. 可透過按鈕完成所有必要操作。
24. 語音為 enhancement，不得取代按鈕 fallback。
25. 小型 LLM failure 不得讓遊戲失效。

---

# 41. 非目標

v1.0 明確不做：

```text
Large VLM
Cloud GPT
Full free-form AI Dungeon Master
3D rendering
AR glasses
Indoor floor positioning
SLAM
完整導航
多人線上 RPG
大型 open-world map streaming
大型 procedural 3D world
大型 speech model
LLM-controlled world state
```

---

# 42. 最終產品定義

本專案不是：

```text
Camera → AI → 隨機編故事
```

而是：

```text
Real-world position
        +
Real-world visual environment
        ↓
FRDM-i.MX93 Edge Perception
        ↓
Persistent Spatial World
        ↓
Exploration Progress
        ↓
Safe Event Trigger
        ↓
Structured RPG Simulation
        ↓
Optional Small Local Dialogue AI
        ↓
2D Reality-based Exploration RPG
```

最重要的設計原則：

> **Reality determines context.
> Rules determine the world.
> AI improves presentation.**

AI 不掌控遊戲真相。

SQLite World State 才是遊戲真相。

---

# 43. Astra 最終實作策略

不要一次實作全部功能。

優先建立：

```text
Phone GPS
→ Map
→ H3
→ Fog of War
→ Exploration
→ SQLite
```

確認探索核心穩定後才加入：

```text
Camera
→ Vision
→ RPG mapping
→ Event Engine
```

確認遊戲循環穩定後才加入：

```text
Voice
→ NPC
→ Small LLM
```

如果最後小型 LLM 在 Cortex-A55 上效能不理想：

**不要改成 Cloud。**

直接：

```text
Template NPC Dialogue
+
Structured choices
```

完成第一版。

本專案的成功標準是：

> FRDM-i.MX93 能完全離線地將玩家的真實戶外移動與環境轉換成一個持久、可探索、有事件、有 NPC、有任務的 2D RPG 世界。

而不是追求大型模型能力。
