# Exports Directory

This directory stores master render files, final exported MP4 videos, complete YouTube metadata packages, and signed pre-publish checklists ready for human review and channel upload.

## Directory Structure Per Topic

```text
exports/
└── <topic-slug>/
    ├── YYYYMMDD-<topic-slug>.mp4     # Master video render (H.264, 1080×1920 or 1920×1080)
    ├── metadata.md                   # Title options, description, tags, thumbnail concept
    ├── checklist.md                  # Pre-publish verification & human approval checklist
    └── thumbnail/                    # Optional exported thumbnail image assets
        └── thumbnail-concept.png
```

## Production Gate Rules
1. Never upload or distribute any file from `exports/` without a completed `checklist.md` bearing human creator sign-off.
2. Ensure every exported video has been checked via `ffprobe` and reviewed by `video-quality-reviewer`.
