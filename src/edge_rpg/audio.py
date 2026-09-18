import array
import difflib
import logging
import math
import re
import subprocess
import tempfile
import threading
import time
import wave
from .messages import Kind

COMMANDS = {
    "打開地圖":"MAP", "地圖":"MAP", "調查":"INSPECT", "調查這裡":"INSPECT",
    "交談":"TALK", "我想跟他說話":"TALK", "接受":"ACCEPT", "拒絕":"REFUSE",
    "離開":"LEAVE", "我要離開":"LEAVE", "查看任務":"QUESTS", "查看背包":"INVENTORY",
    "map":"MAP", "inspect":"INSPECT", "talk":"TALK", "accept":"ACCEPT", "refuse":"REFUSE",
    "leave":"LEAVE", "quests":"QUESTS", "inventory":"INVENTORY",
    "打开地图":"MAP", "地图":"MAP", "调查":"INSPECT", "调查这里":"INSPECT",
    "交谈":"TALK", "我想跟他说话":"TALK", "拒绝":"REFUSE", "离开":"LEAVE",
    "我要离开":"LEAVE", "查看任务":"QUESTS",
}


def parse_intent(text):
    normalized = re.sub(r'[\s。！!，,.?？]','',text.lower())
    if normalized in COMMANDS:
        return COMMANDS[normalized]
    # Avoid matching "不要接受" or a long sentence with contradictory intent.
    if any(word in normalized for word in ("不要","不想","別","别","don't","not")):
        return "UNKNOWN"
    matches = difflib.get_close_matches(normalized,COMMANDS,n=2,cutoff=0.88)
    return COMMANDS[matches[0]] if len(matches)==1 else "UNKNOWN"


class AudioWorker:
    def __init__(self,cfg,bus,gate):
        self.cfg,self.bus,self.gate = cfg,bus,gate
        self.stop = threading.Event()
        self.process = None
        self.status = "disabled"
        self.latency_ms = 0
        self.thread = threading.Thread(target=self.run,daemon=True,name="audio-asr")
        self.thread.start()

    def recognize(self,pcm):
        if not self.cfg["command"]:
            self.status = "ASR model not configured"
            return
        with tempfile.NamedTemporaryFile(suffix='.wav') as tmp:
            with wave.open(tmp.name,'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.cfg["sample_rate"])
                wav.writeframes(pcm)
            argv = [part.replace('{wav}',tmp.name) for part in self.cfg["command"]]
            start = time.monotonic()
            with self.gate.lock:
                text = subprocess.run(argv,capture_output=True,text=True,timeout=self.cfg["timeout_sec"],check=True).stdout.strip()
            self.latency_ms = (time.monotonic()-start)*1000
            self.bus.publish(Kind.VOICE_INTENT,intent=parse_intent(text))

    def run(self):
        if not self.cfg["enabled"]:
            return
        try:
            self.process = subprocess.Popen(['arecord','-q','-D',self.cfg['device'],'-t','raw','-f','S16_LE','-c','1','-r',str(self.cfg['sample_rate'])],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            self.status = "listening"
            chunks, silence = [], 0
            size = int(self.cfg['sample_rate']*0.02)*2
            while not self.stop.is_set():
                pcm = self.process.stdout.read(size)
                if len(pcm) != size:
                    raise OSError("Microphone disconnected")
                values = array.array('h',pcm)
                rms = math.sqrt(sum(v*v for v in values)/len(values))
                active = rms >= self.cfg['vad_rms']
                if active or chunks:
                    chunks.append(pcm)
                    silence = 0 if active else silence+0.02
                    if silence >= self.cfg['silence_sec'] or len(chunks)*0.02 >= self.cfg['max_segment_sec']:
                        try:
                            self.recognize(b''.join(chunks))
                        except (OSError,subprocess.SubprocessError) as exc:
                            self.status = "ASR unavailable"
                            logging.getLogger('ASR').warning('asr_failed error=%s',exc)
                        chunks,silence = [],0
        except OSError as exc:
            self.status = "microphone unavailable"
            logging.getLogger('AUDIO').warning('microphone_unavailable error=%s',exc)
        finally:
            if self.process:
                self.process.terminate()
                self.process.wait(timeout=2)

    def close(self):
        self.stop.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.thread.join(timeout=3)
