---
name: video-editor
description: Assemble final video from rendered scenes, audio, captions using FFmpeg. Applies quality-checked edits.
---

## Purpose
Concatenate rendered scenes, mix narration, burn captions, and export a final QC-ready MP4.

## FFmpeg Operations
| Task | Filter / Flag |
|------|--------------|
| Concatenate | `concat` demuxer with `list.txt` |
| Caption burn | `drawtext` — white, 48 px min, bottom-third |
| Audio mix | `amix` or `amerge` |
| Fade in/out | `fade=t=in:st=0:d=0.5` |
| Speed adjust | `setpts=0.5*PTS` (2× speed) |

## Standard Export
```bash
ffmpeg -i input.mp4 -c:v libx264 -preset slow -crf 23 \
       -c:a aac -b:a 128k -movflags +faststart output.mp4
```

## Shorts Export (append to above)
```bash
-vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:-1:-1"
```

## Caption Style
- Font: white, shadow or dark box background
- Position: bottom third (y=H*0.80)
- Minimum size: 48 px equivalent at 1080p

## QC Checklist (run ffprobe on output)
- [ ] Duration matches script total
- [ ] No black frames at start or end
- [ ] Audio stream present and audible
- [ ] Resolution matches target spec

## Session Log
Append every run to `editing/session-log.md`:
```
Date | Input files | Output | Duration | Notes
```

## Output
`renders/<topic>/final.mp4` → `renders/<topic>/final-captioned.mp4`
