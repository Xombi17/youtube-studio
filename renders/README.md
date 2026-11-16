# Renders Directory

This directory stores intermediate visual assets, scene-by-scene MP4 clips, rendered narration audio files, and assembly builds generated during Stage 5, Stage 6, Stage 7, and Stage 8 of the CreatorRadar production pipeline.

## Directory Structure Per Topic

```text
renders/
└── <topic-slug>/
    ├── scenes/
    │   ├── scene-01.mp4
    │   ├── scene-02.mp4
    │   └── ...
    ├── audio/
    │   ├── narration.wav
    │   └── background_music.wav
    ├── rough-cut.mp4
    └── final-captioned.mp4
```

## Retention Policy
- Intermediate scene files can be purged after final export verification.
- Always retain `final-captioned.mp4` until the corresponding export is approved by human review.
