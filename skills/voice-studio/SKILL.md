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

## Studio Policy Compliance
- Voice cloning is strictly authorized for the channel owner's voice.
- Never clone third-party or celebrity voices without explicit written rights.
- Disclose AI-assisted voiceover processing in video descriptions as required by YouTube policy.
