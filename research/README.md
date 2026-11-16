# Research Directory

This directory acts as the single source of truth for factual claims across all CreatorRadar video topics.

## Core Principles
1. **Zero Fabrication:** Never publish or script any claim that is not substantiated by an authoritative primary source.
2. **Permanent Audit Trail:** Never delete or alter source references once published.
3. **Traceability:** Every claim in a video script must map to a specific `Claim ID` in that topic's `claims.md`.

## Directory Structure Per Topic

```text
research/
├── gta6-core/             # Universal verified facts database for GTA VI
│   └── claims.md
└── <topic-slug>/          # Topic-specific claim ledgers
    └── claims.md          # Claim ID, Claim, Source URL, Date, Confidence, Notes
```

## Confidence Levels
- **HIGH:** Official publisher announcements, direct manufacturer support manuals, or live console storefront entries.
- **MEDIUM:** Established industry reporting citing verified on-the-record developer statements.
- **LOW / UNCONFIRMED:** Rumors, leaks, or speculation — strictly prohibited in tutorial scripts.
