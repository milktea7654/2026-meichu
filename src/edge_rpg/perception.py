"""On-demand V4L2 capture and quantized TFLite classifier + SSD detector."""
import logging
import threading
import time
from pathlib import Path
import numpy as np
from PIL import Image
from .messages import Kind


def fingerprint(rgb):
    # Store a compact thumbnail, not camera frames; compare absolute appearance distance.
    return np.asarray(Image.fromarray(rgb).convert('L').resize((16,8)),dtype=np.uint8).tobytes().hex()


class InferenceGate:
    """Serialize vision, ASR, and optional text inference on a 2 GB host."""
    def __init__(self):
        self.lock = threading.Lock()


class TFLiteModel:
    def __init__(self, path, delegate, scale, offset):
        from tflite_runtime.interpreter import Interpreter, load_delegate
        delegates = [load_delegate(delegate)] if delegate else []
        self.runtime = Interpreter(model_path=path,experimental_delegates=delegates,num_threads=2)
        self.runtime.allocate_tensors()
        self.input = self.runtime.get_input_details()[0]
        self.outputs = self.runtime.get_output_details()
        self.scale, self.offset = scale, offset

    def infer(self, rgb):
        _, height, width, channels = self.input["shape"]
        if channels != 3:
            raise ValueError("Vision models require NHWC RGB input")
        values = np.asarray(Image.fromarray(rgb).resize((int(width),int(height))),dtype=np.float32)*self.scale+self.offset
        dtype = self.input["dtype"]
        if np.issubdtype(dtype,np.integer):
            scale,zero = self.input["quantization"]
            if scale <= 0:
                raise ValueError("Quantized model missing input scale")
            limits = np.iinfo(dtype)
            values = np.clip(np.rint(values/scale+zero),limits.min,limits.max)
        self.runtime.set_tensor(self.input["index"],values.astype(dtype)[None])
        self.runtime.invoke()
        results = []
        for output in self.outputs:
            value = self.runtime.get_tensor(output["index"])
            scale,zero = output["quantization"]
            if scale:
                value = (value.astype(np.float32)-zero)*scale
            results.append(value)
        return results


class VisionBackend:
    def __init__(self,cfg):
        self.cfg = cfg
        args = (cfg["delegate"],cfg["input_scale"],cfg["input_offset"])
        self.scene_model = TFLiteModel(cfg["classifier"],*args)
        self.object_model = TFLiteModel(cfg["detector"],*args)
        self.scenes = Path(cfg["classifier_labels"]).read_text().splitlines()
        self.objects = Path(cfg["detector_labels"]).read_text().splitlines()

    def analyze(self,rgb):
        scores = self.scene_model.infer(rgb)[0].reshape(-1)
        if len(scores) != len(self.scenes):
            raise ValueError("Classifier labels/output mismatch")
        index = int(np.argmax(scores))
        detected = self.object_model.infer(rgb)
        mapping = self.cfg["detector_outputs"]
        classes = detected[mapping["classes"]].reshape(-1)
        probabilities = detected[mapping["scores"]].reshape(-1)
        count = min(int(detected[mapping["count"]].reshape(-1)[0]),len(classes),len(probabilities))
        objects = []
        for i in range(count):
            idx = int(classes[i])+self.cfg["detector_class_offset"]
            if 0 <= idx < len(self.objects) and probabilities[i] >= self.cfg["confidence"]:
                objects.append({"class":self.objects[idx],"confidence":float(probabilities[i])})
        return {"timestamp":time.time(),"scene":self.scenes[index],"scene_confidence":float(scores[index]),"objects":objects,
                "indoor_probability":float(scores[self.scenes.index("indoor")]) if "indoor" in self.scenes else 1.0}


class VisionWorker:
    def __init__(self,cfg,bus,gate):
        self.cfg,self.bus,self.gate = cfg,bus,gate
        self.requested = None
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.status = "idle"
        self.latency_ms = 0
        self.camera_fps = 0
        self.thread = threading.Thread(target=self.run,daemon=True,name="vision")
        self.thread.start()

    def request(self, cell):
        self.requested = cell
        self.wake.set()

    def run(self):
        backend = None
        while not self.stop.is_set():
            if not self.wake.wait(0.2):
                continue
            self.wake.clear()
            cell = self.requested
            if not cell or not self.cfg["enabled"]:
                continue
            capture = None
            try:
                import cv2
                with self.gate.lock:
                    if backend is None:
                        backend = VisionBackend(self.cfg)
                    capture = cv2.VideoCapture(self.cfg["camera"],cv2.CAP_V4L2)
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH,self.cfg["width"])
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT,self.cfg["height"])
                    capture.set(cv2.CAP_PROP_BUFFERSIZE,1)
                    if not capture.isOpened():
                        raise RuntimeError("Camera unavailable")
                    self.status = "analyzing"
                    deadline = time.monotonic()+self.cfg["analysis_duration_sec"]
                    while time.monotonic() < deadline and not self.stop.is_set() and self.requested == cell:
                        start = time.monotonic()
                        ok, frame = capture.read()
                        if not ok:
                            raise RuntimeError("Camera capture failed")
                        rgb = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                        inference_start = time.monotonic()
                        observation = backend.analyze(rgb)
                        self.latency_ms = (time.monotonic()-inference_start)*1000
                        self.bus.publish(Kind.SCENE_OBSERVED, cell_id=cell,observation=observation,fingerprint=fingerprint(rgb))
                        self.stop.wait(max(0,1/self.cfg["fps"]-(time.monotonic()-start)))
                        self.camera_fps = 1/max(0.001,time.monotonic()-start)
                    self.status = "idle"
            except Exception as exc:
                self.status = f"unavailable: {type(exc).__name__}"
                logging.getLogger("VISION").warning("vision_unavailable error=%s",exc)
            finally:
                if capture is not None:
                    capture.release()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=2)
