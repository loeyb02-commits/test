"""Render a synthetic pen gesture to WAV, without audio hardware or Wintab."""
from array import array
from pathlib import Path
import math
import sys
import wave
from penasmr.core import Friction, Motion

def render(path):
    engine = Friction()
    engine.rng.seed(42)
    with wave.open(str(path),'wb') as wav:
        wav.setparams((1,2,48000,0,'NONE','not compressed'))
        for block in range(1125): # six seconds: slow/light, fast/firm, silence
            t=block*256/48000
            speed,pressure=(.06,.2) if t<2 else ((.4,.9) if t<4 else (0.,0.))
            values=array('f',engine.render(256,Motion(speed,pressure,t),t))
            pcm=array('h',(int(v*32767) for v in values))
            if sys.byteorder!='little': pcm.byteswap()
            wav.writeframes(pcm.tobytes())
    print(Path(path).resolve())

if __name__=='__main__':
    render(sys.argv[1] if len(sys.argv)>1 else 'demo.wav')
