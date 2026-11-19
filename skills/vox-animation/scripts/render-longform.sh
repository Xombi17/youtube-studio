#!/usr/bin/env bash
# render.sh [seconds]  — frame-step compose.html, mux the voice, export H.264.
# With no argument it renders the full length from timings.json.
set -euo pipefail
cd "$(dirname "$0")"
SECS="${1:-0}"; FPS=30
[ -f timings.json ] || { echo "run fish-tts first"; exit 1; }
MS=$(python3 -c "import json;print(json.load(open('timings.json'))['total_ms'])")
if [ "$SECS" = "0" ]; then
  FRAMES=$(python3 -c "print(int(round(($MS+900)/1000*$FPS)))")
else
  FRAMES=$(( SECS * FPS ))
fi
echo "  $FRAMES frames @ ${FPS}fps"
mkdir -p out
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

node - compose.html "$TMP" "$FRAMES" "$FPS" <<'JS'
process.env.PUPPETEER_SKIP_CHROME_DOWNLOAD='1';
const path=require('path');
const puppeteer=require(path.join(process.env.HOME,'Desktop/infographic-generator/node_modules/puppeteer'));
(async()=>{
  const [src,out,frames,fps]=process.argv.slice(2);
  const b=await puppeteer.launch({args:['--no-sandbox','--force-color-profile=srgb']});
  const p=await b.newPage();
  p.on('pageerror',e=>console.error('[page]',e.message));
  p.on('console',m=>{ if(m.type()==='error') console.error('[console]',m.text()); });
  await p.setViewport({width:1920,height:1080,deviceScaleFactor:1});
  await p.goto('file://'+path.resolve(src),{waitUntil:'networkidle0'});
  await p.evaluate(async()=>{ if(window.READY) await window.READY; });
  const n=Number(frames);
  for(let i=0;i<n;i++){
    await p.evaluate(async(t)=>{ await window.seek(t); },(i/Number(fps))*1000);
    await p.screenshot({path:path.join(out,String(i).padStart(6,'0')+'.jpg'),type:'jpeg',quality:92});
    if(i%300===0) process.stderr.write(`    ${i}/${n}\n`);
  }
  await b.close();
})();
JS

ffmpeg -y -loglevel error -framerate $FPS -i "$TMP/%06d.jpg" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r $FPS out/raw.mp4
REAL=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 out/raw.mp4)
echo "  out/raw.mp4 ${REAL} frames (expected ${FRAMES})"
[ "$REAL" -ge "$(( FRAMES - 2 ))" ] || { echo "  TRUNCATED — do not ship"; exit 2; }

if [ "$SECS" = "0" ]; then
  ffmpeg -y -loglevel error -i out/raw.mp4 -i audio/vo.mp3 \
    -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest out/with-vo.mp4
  ffmpeg -y -loglevel error -i out/with-vo.mp4 -c:v libx264 -profile:v high -preset slow \
    -pix_fmt yuv420p -vf "scale=1920:1080:in_range=full:out_range=limited,format=yuv420p" \
    -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
    -b:v 12M -maxrate 14M -bufsize 20M -c:a aac -b:a 192k -ar 48000 -movflags +faststart \
    out/neural-networks.mp4
  ffprobe -v error -select_streams v:0 \
    -show_entries stream=codec_name,width,height,color_range,nb_frames \
    -show_entries format=duration -of default=nw=1 out/neural-networks.mp4
  echo "  $(pwd)/out/neural-networks.mp4"
fi
