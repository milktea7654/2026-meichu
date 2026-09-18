# 本地模型部署契約

程式庫不包含模型權重，也不以假分類結果冒充模型。`--demo` 的 synthetic observations 僅供展示與測試。

## Vision

`models/vision/scene_vela.tflite`：NHWC RGB、batch 1、uint8/int8 量化 classifier，單一輸出是依 label 順序排列的 **probabilities**，非未經 softmax logits。

`models/vision/scenes.txt`：一行一 class，至少包含 `indoor`。缺少 indoor class 時以 indoor_probability=1 fail closed。建議 park/road/campus/plaza/trail/forest_like/riverside/lake_side/urban_outdoor/unknown/indoor。

`models/vision/detector_vela.tflite`：NHWC RGB、SSD-style detection。`detector_outputs` 依 `get_output_details()` 的 list index 設定 boxes/classes/scores/count，不是 tensor ID。`detector_class_offset` 校正 class index；objects.txt 一行一 label，約 15–30 類。YOLO raw head 必須先另加 decoder，不能直接假設支援。

`input_scale` / `input_offset` 定義 float-domain pixel transform，之後使用模型 tensor 的 quantization scale/zero-point 換算 dtype。**必須依實際模型訓練 preprocessing 修改**；目前預設 RGB/255。若兩模型 preprocessing 不同，需分別轉換成一致契約或擴充 per-model 設定後再部署。

使用 NXP BSP 相容的 `tflite_runtime` 和 `/usr/lib/libethosu_delegate.so`。先以對應 BSP 的 Vela compiler 編譯相同 Ethos-U 配置，再跑 BSP benchmark tool；不要猜 compiler accelerator_config 或直接沿用其他板子的 delegate。

NXP 提供 [Ethos-U delegate 原始碼](https://github.com/nxp-imx/tflite-ethosu-delegate-imx) 及 [FRDM 官方入門／benchmark 範例](https://www.nxp.com/document/guide/getting-started-with-frdm-imx93%3AGS-FRDM-IMX93)。實際模型轉換與 fallback operators 須以 BSP 的 [ML User's Guide](https://www.nxp.com/docs/en/user-guide/UG10166.pdf) 對應版本為準。

部署前記錄：模型來源／license／SHA-256、class order、shape、quantization、preprocessing、Vela/BSP version、CPU fallback operators、P50/P95 latency、memory 和真實戶外／室內測試結果。尚未有這些實測證據，Phase 4 不能標示驗收完成。

## Voice（可選）

先安裝 ALSA `arecord`，確認 16 kHz mono capture。再安裝 ARM64 相容 sherpa-onnx 和本地模型。

提供 `scripts/sherpa_transcribe.py` 作為 SenseVoice WAV adapter。依 [上游 Python API](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/python/sherpa_onnx/offline_recognizer.py) 使用 `OfflineRecognizer.from_sense_voice`。模型的實際 RAM／latency 必須測量，不能假設一定符合 350 MB target；不符合就保留按鈕或換更小的本地 command recognizer。

```yaml
audio:
  enabled: true
  device: default
  sample_rate: 16000
  vad_rms: 450
  silence_sec: 0.6
  max_segment_sec: 5
  command:
    - /opt/fieldbound/.venv/bin/python
    - /opt/fieldbound/scripts/sherpa_transcribe.py
    - --model
    - /opt/fieldbound/models/speech/model.int8.onnx
    - --tokens
    - /opt/fieldbound/models/speech/tokens.txt
    - '{wav}'
  timeout_sec: 8
```

VAD 是 energy-based，戶外風噪可能誤觸發；聲學可靠性必須在板子驗收。CLI stdout 僅輸出 transcript，diagnostics 寫 stderr。固定中文命令與 English buttons 共用 deterministic intent parser；模糊／否定命令回 UNKNOWN。

## Dialogue（可選）

Template 是完整可玩預設。若部署通過驗證的 300M–600M Q4 GGUF，可設定 `dialogue.llm_enabled: true`、`model` 與本地 `llama-cli` executable。

採 ephemeral CLI，context=1024、max output=64、timeout=8s；失敗即 template。Prompt 使用 structured facts，回應不會被執行為命令。輸出還要通過保守 closed-vocabulary 檢查，因此任意自由文字很可能退回模板；這是 MVP 的有限對話範圍，不宣稱支援自由聊天。模型效能不佳時保持關閉，沒有 cloud fallback。
