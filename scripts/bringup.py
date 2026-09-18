#!/usr/bin/env python3
"""Read-only board diagnostic. --capture briefly exercises camera/microphone."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import tempfile

p=argparse.ArgumentParser()
p.add_argument('--capture',action='store_true')
p.add_argument('--camera',default='/dev/video0')
p.add_argument('--audio',default='default')
a=p.parse_args()
report={'architecture':platform.machine(),'kernel':platform.release(),
        'camera':Path(a.camera).exists(),'ethosu':list(map(str,Path('/dev').glob('ethosu*'))),
        'delegate':Path('/usr/lib/libethosu_delegate.so').exists(),
        'display':{'DISPLAY':os.getenv('DISPLAY'),'WAYLAND_DISPLAY':os.getenv('WAYLAND_DISPLAY'),'drm':list(map(str,Path('/dev/dri').glob('*')))},
        'meminfo':Path('/proc/meminfo').read_text().splitlines()[:3]}
for name in ['h3','pygame','yaml','websockets','cv2','tflite_runtime']:
    report[name]=importlib.util.find_spec(name) is not None
for name,cmd in [('network',['ip','-brief','address']),('audio_devices',['arecord','-l'])]:
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
        report[name]={'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    except (OSError,subprocess.SubprocessError) as exc:
        report[name]=str(exc)
with tempfile.TemporaryDirectory() as root:
    db=sqlite3.connect(str(Path(root)/'probe.db'))
    db.execute('CREATE TABLE probe(value INTEGER)'); db.execute('INSERT INTO probe VALUES(1)'); db.commit()
    report['sqlite']=db.execute('SELECT value FROM probe').fetchone()[0]==1
    db.close()
    if a.capture:
        try:
            import cv2
            cap=cv2.VideoCapture(a.camera,cv2.CAP_V4L2)
            ok,frame=cap.read()
            report['camera_capture']=bool(ok)
            report['camera_shape']=list(frame.shape) if ok else None
            cap.release()
        except Exception as exc: report['camera_capture']=str(exc)
        try:
            r=subprocess.run(['arecord','-q','-D',a.audio,'-d','2','-r','16000','-c','1','-f','S16_LE',str(Path(root)/'probe.wav')],capture_output=True,text=True,timeout=5)
            report['audio_capture']={'exit':r.returncode,'stderr':r.stderr}
        except (OSError,subprocess.SubprocessError) as exc: report['audio_capture']=str(exc)
print(json.dumps(report,indent=2))
