# Host validation — 2026-09-18

Environment: Python 3.11.14, x86_64 WSL Linux. This is not FRDM hardware evidence.

## Automated regression

Command: `PYTHONPATH=src .venv/bin/python -m pytest -q`

Result in an environment permitting loopback sockets: **39 passed in 1.54s**, no skips.

In the restricted socket sandbox: **38 passed, 1 skipped**. The skipped test is the real WebSocket loopback test, which passed when rerun with local socket access.

## Executable / UI

`SDL_VIDEODRIVER=dummy PYTHONPATH=src .venv/bin/python -m edge_rpg.app --demo --port 0 --seconds 3 --screenshot docs/evidence/host-ui.png`

Exit code 0. Board process binds an available port, runs the SDL UI, displays synthetic GPS/H3 progress, exports a 1280×720 PNG, then closes the server. The screenshot is a simulation without real map tiles or vision models.

## Installation

The editable project installation and `edge-rpg --help` entry point were exercised with the workspace virtual environment.

## Unverified

FRDM boot/HDMI/Wi-Fi/camera/ALSA, NPU delegated inference, 2 GB board resource budget, Android APK build/device GNSS, actual area geofences/MBTiles, ASR acoustic recognition and GGUF generation quality. No credentials, field assets or compatible model weights were supplied.

## Follow-up: exact geofence trajectories and invalid scene isolation

Replaced metre-spaced geofence samples with polygon boundary intersection
intervals. Added regressions for a centimetre-wide blocked strip, allowed-area
holes/gaps/unions, tangency, stationary points, and non-finite coordinates.
Scene observations now undergo complete schema validation before updating the
world's latest scene, and mutable backend data is copied. Invalid scene output
revokes the previous scene clearance and cannot crash the next GPS update.

Restricted sandbox regression: **58 passed, 1 skipped** (loopback socket).

Full follow-up regression with loopback socket access: **59 passed in 1.98s**, no skips.

## Android APK follow-up

The prior unverified APK-build item has now been completed. Installed official
Android SDK 35/build-tools 34.0.0 and a complete Temurin JDK 17 under a temporary
build-tool directory. Added the official Gradle 8.9 wrapper with a distribution
SHA-256 pinned against the official distribution checksum. The system Java
runtime lacked jlink; the complete JDK resolved this toolchain failure.

Final command used the checked-in wrapper:

`./gradlew :app:assembleDebug :app:lintDebug --offline --no-daemon --console=plain`

Result: **BUILD SUCCESSFUL**, **No issues found** by Android lint. `apksigner
verify --verbose` verifies the resulting APK (v2 scheme). Evidence is recorded in
`android-build.txt`, `android-lint.txt`, `android-signature.txt`, and
`android-apk.sha256` alongside this file.

APK: `apps/android_gps_bridge/app/build/outputs/apk/debug/app-debug.apk`.
The app now has English/Traditional Chinese resources and explicit backup
exclusions. No phone/emulator runtime or outdoor GNSS testing has been performed;
those still require a device. FRDM/model/field-data blockers are unchanged.
