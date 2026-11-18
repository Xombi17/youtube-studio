---
name: voice-studio
description: Local voice cloning and speech synthesis integration using VoiceStudio (http://localhost:3900).
---

# VoiceStudio Integration

Uses Palash Debnath's open-source [VoiceStudio](https://github.com/debpalash/VoiceStudio) as the primary offline voice cloning engine for CreatorRadar voiceovers.

## Architecture & Endpoints
VoiceStudio exposes a local REST API on port 3900:
- **Base URL:** `http://localhost:3900`
- **Health Check:** `GET /health`
- **Model / Voice Registry:** `GET /models`
- **TTS & Voice Clone Synthesizer:** `POST /tts` (or engine-specific cloning endpoint)

## Voice Setup Workflow
1. **Sample Collection:** Record 1–3 minutes of clear, uncompressed speech (24kHz or 48kHz WAV) without background noise.
2. **Profile Creation:** Save the reference sample in `assets/voices/creator_sample.wav`.
3. **VoiceStudio Profile:** In VoiceStudio desktop UI or API, enroll `creator_sample.wav` as the primary voice profile (named `creator-voice`).
4. **Automated Synthesis:** When `ai-video-generator` or `tutorial-scriptwriter` generates a script beat, invoke `scripts/voice_studio_client.py` to synthesize speech using the cloned voice.
5. **Fallback:** If VoiceStudio is offline or not running, the client falls back to local neural/system TTS with a log notice.

## Expressive Voice Modulation & Pacing Standards (Mandatory)
- **Use Expressive `ChatterboxTTS` (Standard), NOT flat `ChatterboxTurboTTS`, for creator narration:** `ChatterboxTurboTTS` ignores `exaggeration` and `cfg_weight`, producing monotone cadence. Use `from chatterbox.tts import ChatterboxTTS` with **`exaggeration = 0.65–0.85`** (higher on hooks, twists, and exclamations) and **`cfg_weight = 0.40–0.48`** for deliberate, human storyteller modulation.
- **Clause-Directed Punctuation & Micro-Pauses:** Synthesize beats in short expressive clauses using real `?`, `!`, and `...` punctuation, then stitch clauses with intentional **`0.14s–0.22s`** breathing pauses so questions rise naturally and punchlines hit with real vocal emphasis.
- **Whisper Pronunciation Verification:** Generate multi-take candidates per clause and verify `>= 0.98` word accuracy via Whisper before mastering.
- **Seamless Loop Bridge Recording & Stem Handoff (v2 Standard):** When possible, synthesize/record the ending loop bridge and the repeated opening phrase in one continuous take, then trim the repeated opening cleanly at its word boundary so cadence flows invisibly back into `t = 0.00s` (`<= 0.05s` onset, `<= 0.10s` tail). Export the final dialogue stem as full-length, sample-aligned **48 kHz / 24-bit WAV** starting at sample zero, and never treat automated signal metrics as a substitute for a direct listening check.

## Studio Policy Compliance
- Voice cloning is strictly authorized for the channel owner's voice.
- Never clone third-party or celebrity voices without explicit written rights.
- Disclose AI-assisted voiceover processing in video descriptions as required by YouTube policy.
