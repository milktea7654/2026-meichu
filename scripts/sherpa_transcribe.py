#!/usr/bin/env python3
"""Local sherpa-onnx SenseVoice WAV adapter; invoked on demand, stdout is text only."""
import argparse
import wave
import numpy as np
import sherpa_onnx

p=argparse.ArgumentParser()
p.add_argument('--model',required=True)
p.add_argument('--tokens',required=True)
p.add_argument('--threads',type=int,default=2)
p.add_argument('wav')
a=p.parse_args()
with wave.open(a.wav) as f:
    if f.getnchannels()!=1 or f.getsampwidth()!=2 or f.getframerate()!=16000:
        raise ValueError('Expected 16 kHz mono S16LE')
    samples=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float32)/32768
recognizer=sherpa_onnx.OfflineRecognizer.from_sense_voice(model=a.model,tokens=a.tokens,num_threads=a.threads,use_itn=True,debug=False)
stream=recognizer.create_stream()
stream.accept_waveform(16000,samples)
recognizer.decode_stream(stream)
print(stream.result.text)
