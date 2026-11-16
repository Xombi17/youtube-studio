---
name: style-selector
description: Automatically evaluates and matches video scripts against all 21 Claude Video 2.0 and 99 Lemo-Opuscar motion graphic styles. Selects the optimal look, hex palette, typography, easing curves, and camera motion rules.
---

# Style Selector Skill

Analyzes script text, keyword density, pacing, and visual intent to match the script to the most engaging motion graphic style in `styles/`.

## Usage

```bash
python3 scripts/select_style.py <path_to_script.md>
```

Returns structured JSON with:
- `selected_style`: ID of the winning look (e.g. `midnight-grid`, `swiss-kinetic`, `explainer-diagram`, `blueprint`)
- `confidence_score`: Match weight based on domain terminology
- `palette`: Required hex color codes
- `motion`: Easing curves, tempo (BPM), and signature animation behaviors
