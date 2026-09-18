# FRDM 部署／現場操作

## 0. Bring-up

以 NXP 適用於 FRDM-i.MX93 的 Yocto BSP 啟動，確認 Wi-Fi、HDMI/Wayland、V4L2 和 ALSA。沒有板子 SSH 資訊時無法由此工作區執行這些步驟。

```sh
python3 scripts/bringup.py --capture > bringup-report.json
```

此命令個別驗證介面；capture 僅短暫讀相機和麥克風。須人工確認 HDMI 畫面、板端 GNSS 移動方向和 Wi-Fi 穩定性。bringup-report 顯示 false／missing 不是通過。

## 1. Runtime 安裝

將 repo 放 `/opt/fieldbound`，資料路徑可在 game.yaml 改成可寫的持久分割區。Python 3.11+，SQLite、SDL2、SDL_ttf／字型、h3、PyYAML、websockets、pygame-ce、numpy、Pillow。Yocto 上 OpenCV 與 TFLite 建議使用 BSP 相容套件；不要用 x86 wheel 搬到 ARM64。

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e .
```

離線部署前，於相同 aarch64/Python ABI 的 staging 環境準備 wheelhouse：

```sh
python3 -m pip wheel . -w wheelhouse
python3 -m pip install --no-index --find-links=wheelhouse edge-exploration-rpg
```

`requirements.lock` 記錄這次 x86 主機測試版本；不代表 BSP 上所有 pinned binary wheels 都相容。若 Yocto Python/NumPy ABI 不同，需用該 BSP SDK build 並重跑測試。

## 2. 場域設定

- 預設 allowed FeatureCollection 空白：先填入實際公園／校園公共戶外 polygon。
- blocked file 包含建築、水域、工地、私人空間、危險道路。支援 Polygon/MultiPolygon 與內環。
- Raster MBTiles metadata 應包含 format、attribution；UI 會顯示 attribution。現有 renderer 不支援 vector PBF tiles。
- 離線 tiles 取得與授權由場域資料提供者負責；程式沒有自動大量抓取 public tile server 的功能。
- `ui.font` 可設定板端中文字型檔。沒有 tiles 不 crash，但「真實底圖」驗收須提供場域資料。
- 時間以 Unix milliseconds 驗證；板子和手機需在啟動前同步到合理一致的時間。誤差超過 future/stale tolerance 會拒絕 GPS。執行時不依賴在線 NTP。

## 3. Android bridge

開啟 `apps/android_gps_bridge` 於 Android Studio，或使用已安裝 Android SDK 35、JDK 17+、Gradle 8.9：

```sh
cd apps/android_gps_bridge
./gradlew :app:assembleDebug :app:lintDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

AGP 8.7.3 對應 Gradle 8.9，見 [官方相容性表](https://developer.android.com/build/releases/agp-8-7-0-release-notes)。專案附官方 Gradle wrapper，固定 8.9 並驗證分發檔 SHA-256；首次建置會下載相依套件。請使用包含 `javac` 與 `jlink` 的完整 JDK 17+，只有 JRE 無法完成 Android 編譯。

使用 Android framework `LocationManager.GPS_PROVIDER`，不依賴 Google Play Services。開啟熱點、板子連線後輸入 board IP；授予精確定位，保持 app 在前景。Stop／app 進背景會停止 GNSS 並關 socket。WebSocket 掉線指数退避重連，不 replay cached fix。API／permission 依 [Android LocationManager](https://developer.android.com/reference/android/location/LocationManager)；app 不要求背景定位權限。

在共用網路可設定板端 `network.token` 與手機 token。這是本地明文 ws，應使用可信任熱點；GPS 身分／抗偽造不屬 spec 的安全模型。UI 和所有 command 只在板端。

## 4. 啟動與 profile

```sh
.venv/bin/python -m edge_rpg.app
scripts/profile.sh BOARD_APP_PID 60 > profile.txt
```

`deploy/fieldbound.service` 是啟動範本，需依 BSP 的 Wayland session、使用者與 device permissions 調整再安裝。程式不會自動修改開機設定。

分別測正常走動／新格分析／語音／對話，記錄 OS RAM、主程式 RSS、child process RSS、NPU latency 和 headroom。目標是保留 >=200 MB；效能不足先停用 LLM／voice，維持核心與按鈕。

## 5. 真機驗收

照 `docs/acceptance.md` 執行。必須實測拔除 Internet、手機中斷、GPS 精度差、禁區、室內、板子斷電重啟、重入同格和完整 NPC 任務流程。保存 board/BSP/model identity 與 log。不得以 host simulation 替代硬體證據。
