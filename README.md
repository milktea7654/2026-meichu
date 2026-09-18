# Fieldbound — FRDM-i.MX93 Outdoor RPG

依 `spec.md` 實作的板端離線 Python MVP。手機僅傳 GNSS；探索、固定面積方格、地圖、感知、規則、NPC、任務、背包與 SQLite 全在板端執行。板端 UI 使用 pygame-ce / SDL2；另提供瀏覽器 GPS／模擬介面。

**目前可執行／通過主機測試，不代表已完成 FRDM 真機驗收。** 此工作區是 x86_64 WSL，沒有 FRDM、相機、麥克風、NPU、測試場域 MBTiles 或已訓練的場景／物件模型。硬體和模型部署狀態詳見 [驗收追蹤](docs/acceptance.md)。原始 `spec.md` 保留，最新玩法以 [格網與劇情機制](docs/劇情生成與物件機制說明.md) 為準。

## 先用瀏覽器查看 GPS 格網遊戲

```sh
.venv/bin/python -m edge_rpg.simulator --port 8787
```

開啟 http://127.0.0.1:8787 。提供繁體中文遊戲 UI、真實 SQLite 資料表檢視與劇情生成流程解說。真實地圖每格 2,500 m²，首次有效進入就永久點亮，每六個新格觸發一次事件。支援模擬試走、瀏覽器定位與 Android GPS Bridge；模擬與真實定位分別使用 `simulation-grid.db`、`gps-grid.db`。詳細操作見 [模擬器說明](docs/simulator.md)。

## 快速啟動

需要 Python 3.11+。首次安裝需網路；本機遊戲核心不需 Internet；瀏覽器的 OpenStreetMap 底圖需要網路，板端可用離線 MBTiles。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m edge_rpg.app --demo
```

若用 uv：

```sh
uv venv .venv
uv pip install --python .venv/bin/python -e '.[test]'
```

`--demo` 使用明確標示的模擬 GPS／vision、測試範圍和 `/tmp/edge-rpg-demo/world-grid.db`，不會改動正式世界。畫面可看到方格永久點亮與新格計數；demo 約每 50 秒走過一格。模擬世界重啟後保留，清除該 demo 資料庫才會重建。不要將 demo 圍欄當成真實可進入範圍。

正式啟動：

```sh
.venv/bin/python -m edge_rpg.app --config config/game.yaml
```

先完成以下設定：

1. 在 `data/allowed_areas.geojson` 定義已確認可通行的戶外區域，在 `blocked_areas.geojson` 定義禁入 polygon。預設 `require_allowed_area: false`，不要求白名單；需要限制場域時改為 `true`。
2. 放入有合法使用權的 raster MBTiles 到 `assets/map/area.mbtiles`。缺少圖磚時仍顯示方格網。
3. 在 `config/game.yaml` 指定相機、兩個量化 TFLite 模型與 label 檔。模型輸入／輸出契約見 [模型部署](docs/models.md)。沒有模型仍可點亮新格並觸發通用戶外事件；相機只影響故事情境。
4. 將板子連到手機熱點，手機 app 輸入 `ws://BOARD_IP:8765/location`。只有這條 LAN 連線；手機不含遊戲邏輯。
5. 在 HDMI 畫面用按鈕操作，或快捷鍵 `M 地圖 / I 調查 / T 交談 / A 接受 / R 拒絕 / Esc 離開 / Q 任務 / B 背包`。

`--port 0` 可用於測試，讓系統分配空閒 port；log 會列出 port。正式手機連線請使用固定 port。

## Android APK

已以 Android SDK 35、AGP 8.7.3、Gradle 8.9 與完整 JDK 17 建置 debug APK：

`apps/android_gps_bridge/app/build/outputs/apk/debug/app-debug.apk`

提供英文／繁體中文介面；手機定位、連板與戶外走動仍需實機驗證。重新建置可使用專案附帶的 `./gradlew :app:assembleDebug :app:lintDebug`。

## 驗證

```sh
.venv/bin/python -m pytest -q
SDL_VIDEODRIVER=dummy .venv/bin/python -m edge_rpg.app --demo --port 0 --seconds 3 --screenshot /tmp/fieldbound.png
.venv/bin/python scripts/bringup.py
```

測試含 spec T01–T15、SQLite rollback、NPC→接受→道具→交付→完成任務、真實 loopback WebSocket、離線圖磚與無螢幕 UI。Socket 被沙箱禁止時網路測試會明確 skip，應在允許 loopback 的環境再跑。

部署與硬體驗收：[board.md](docs/board.md)。架構／安全不變量：[architecture.md](docs/architecture.md)。
# 2026-meichu
