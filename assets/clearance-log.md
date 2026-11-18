# CreatorRadar — Asset Copyright Clearance Log

Every audio, image, music, font, or video asset used in published CreatorRadar videos must be logged here prior to export (see `config/production-rules.md` §5 and `skills/copyright-checker/SKILL.md`).

| Asset | Path / Source | Type | License / Basis | Status | Attribution Required | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Creator Voice Sample | `assets/voices/creator_sample.wav` | Voiceover | Owned by channel owner | ✅ CLEARED | None | Primary reference for VoiceStudio / Chatterbox cloning |
| Studio SFX Pack (`click`, `impact`, `riser`, `whoosh`) | `assets/sfx/*.wav` | Sound Effects | Studio-generated / royalty-free | ✅ CLEARED | None | Beat transitions in `scripts/generate_broadcast_audio.py` |
| TangoFlux Editorial Music Bed (`vox_editorial_bed.wav`) & Custom Collage SFX | `assets/music/vox_editorial_bed.wav` (TangoFlux local CUDA) | Music & SFX | Locally AI-generated (declare-lab/TangoFlux) | ✅ CLEARED | AI disclosure in description (Rule 5) | Original instrumental bed + foley SFX |
| AI Editorial Risograph Cutouts (6 stickers) | `renders/gta-flu-economics/cutouts/*.png` | Illustration / Cutout | Original AI-generated + Python cutout | ✅ CLEARED | AI disclosure in description (Rule 5) | No third-party photos or logos |
| Procedural HTML5/GSAP Motion Graphics | `scripts/render_scene.py` + `styles/` | Animation | Original code-generated | ✅ CLEARED | AI disclosure in description (Rule 5) | No third-party footage |
| Google Fonts (`Inter`, `JetBrains Mono`, `Geist`, `Anton`, `Space Grotesk`, `IBM Plex Mono`) | Google Fonts CDN + `projects/Shrinkflation_20_vs_25/fonts/Anton-Regular.ttf` | Typography | SIL Open Font License (OFL 1.1) | ✅ CLEARED | None | Commercial YouTube use permitted |
| Bespoke Programmatic SVG Editorial Artwork (`shrinkflation-20-vs-25`) | `renders/shrinkflation-20-vs-25/build_scene.py` | Vector Illustration / Animation | Original code-authored vector SVG (Zero AI raster images) | ✅ CLEARED | None | 100% original unbranded snack bags, scale, receipt, bar chart, shelf tag |
| Rockstar Games GTA VI Official Press Materials | `rockstargames.com/VI` | Reference / Footage | Rockstar Video Policy (commentary/tutorial) | ⚠️ PER-VIDEO | Link official source in description | Never claim first-hand gameplay (Rule 1) |

---

## Adding New Third-Party Assets (Music / B-Roll / Clips)

Before including any YouTube Audio Library track, stock clip, or trailer excerpt in a video, append a row above with:
- Exact source URL and download date
- License terms (e.g., YouTube Audio Library — No Attribution / CC-BY 4.0)
- Exact attribution text to copy into `exports/<slug>/metadata.md`
