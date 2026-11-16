# YouTube production workspace

The reusable local skills are in `skills/<name>/SKILL.md`. Read the matching skill before its task:

| Task | Skill |
| --- | --- |
| Find current video ideas | `trend-scout` |
| Verify claims and collect sources | `source-researcher` |
| Write a vertical video script | `shorts-scriptwriter` |
| Plan shots, typography and motion | `visual-director` |
| Use Indian visual traditions thoughtfully | `indian-art-styles` |
| Clear third-party footage, music and images | `clip-rights-checker` |
| Review a rendered video | `video-quality-reviewer` |
| Interpret channel data | `channel-analyst` |
| Create a Lemo-Opuscar styled film | `lemo-opuscar` (linked to the cached Claude plugin; first-use library setup still required) |
| Research GTA VI facts from authoritative sources | `gta6-researcher` |
| Write tutorial scripts (long-form or Shorts) | `tutorial-scriptwriter` |
| Plan shots, scenes and storyboard for video | `video-director` |
| Generate AI animation scenes with HyperFrames | `ai-video-generator` |
| Assemble and export final video with FFmpeg | `video-editor` |
| Verify all assets are cleared for YouTube use | `copyright-checker` |
| Generate title, description, tags and thumbnail concept | `youtube-seo` |
| Orchestrate the full TOPIC→METADATA pipeline | `production-pipeline` |
| Voice cloning & neural speech synthesis via VoiceStudio | `voice-studio` |
| Select optimal visual motion style across catalogs | `style-selector` |
| Produce Vox-style documentary explainer videos | `vox-explainer` |
| Write script from 21 hook formulas with retention beats | `yt-script` |
| Title & thumbnail pairing linter | `yt-package` |
| Edit decision list from transcript (dead air, filler cues) | `yt-edit` |
| Triage comments and draft replies in voice | `yt-comment` |
| Weekly YouTube content schedule planner | `yt-plan` |
| Outlier video research ranked by channel multiple | `yt-viral` |
| Audience retention curve & cliff diagnostics | `yt-retention` |
| Extract Shorts from long-form video transcript | `yt-shorts` |
| Description, tags, and search query optimization | `yt-seo` |
| Video chapters generator from transcript | `yt-chapters` |
| Channel audit ending in high-leverage single fix | `yt-audit` |

Use installed HyperFrames, Lemo-Opuscar, Impeccable and Taste skills when applicable. The repository packages listed in `README.md` are not available until their installation status says verified. Never publish, upload, or use paid services solely because a skill suggests it.

---

## CreatorRadar — studio rules

These rules apply to every agent working in this workspace and cannot be overridden by task briefs:

1. **No first-hand gameplay claims** — Never claim personal/first-hand gameplay experience of GTA VI. The studio does not own a PS5 or Xbox; we have not played the game ourselves.
2. **No fabricated mechanics** — Never fabricate gameplay mechanics, cheat codes, missions, in-game details, or stats that are not independently verified from authoritative sources.
3. **Always cite official sources for GTA VI facts** — Every GTA VI factual claim must be backed by an official Rockstar Games, PlayStation, or Xbox source. See `config/gta6-sources.md` for the registry of approved sources.
4. **Human approval before upload** — No video, Short, or Community post may be uploaded to YouTube without explicit human (channel owner) approval. Agents prepare content but never publish autonomously.
5. **Label AI-generated content** — Every video or Short that includes AI-generated graphics, animation, voiceover, or narration must include the disclosure line in its YouTube description: *"Graphics created with AI assistance. All facts sourced from official documentation."*
6. **Mandatory voice cloning via VoiceStudio** — Always use the channel owner's cloned voice profile (`assets/voices/creator_sample.wav`) via `scripts/voice_studio_client.py` and VoiceStudio (`http://localhost:3900`). Apply audio compression, EQ presence, and high-energy pacing (~170–175 WPM) to prevent flat or robotic audio.
7. **Mandatory high-retention kinetic motion graphics** — Never render static video cards. All videos must incorporate continuous micro-motion (Ken Burns zooms 1.0x → 1.08x), visual cut punctuations (screen flickers, flash cuts, scanlines), high-contrast glowing elements, and animated captions to prevent audience drop-off.
