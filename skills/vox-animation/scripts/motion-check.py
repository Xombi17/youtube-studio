#!/usr/bin/env python3
"""Sample a finished video and fail on any static run after the first 0.5s."""
import subprocess, sys, os, tempfile
from PIL import Image
src = sys.argv[1]; step = 0.5; thresh = 0.35
dur = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",src]).strip())
tmp = tempfile.mkdtemp(); prev=None; static=[]; n=0
t = 0.0
while t < dur - 0.2:
    f = os.path.join(tmp, f"{n:05d}.png")
    subprocess.run(["ffmpeg","-v","error","-ss",str(t),"-i",src,"-frames:v","1","-vf","scale=192:108,format=gray",f], check=True)
    im = list(Image.open(f).convert("L").getdata())
    if prev is not None:
        d = sum(abs(a-b) for a,b in zip(prev,im))/len(im)
        if d < thresh and t > 0.5: static.append((round(t,2), round(d,3)))
    prev = im; n += 1; t += step
print(f"{src}: {n} samples over {dur:.1f}s, {len(static)} static")
if static:
    print("  STATIC AT:", static[:12]); sys.exit(2)
print("  PASS — no static run")
