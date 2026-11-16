#!/usr/bin/env python3
"""
Automated Style Selector for CreatorRadar Studio.
Analyzes video scripts/topics against the full catalog of:
1. Claude Video 2.0 Motion Graphics (21 styles in styles/)
2. Lemo-Opuscar Code Films (99+ styles in styles/lemo/)
Selects the optimal style with its palette, typography, easing, and motion rules.
"""

import sys
import os
import re
import json
from pathlib import Path

STUDIO_ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parent.parent))
CLAUDE_STYLES_DIR = STUDIO_ROOT / "styles"
LEMO_STYLES_DIR = STUDIO_ROOT / "styles" / "lemo"

STYLE_KEYWORDS = {
    # Hardware, specs, guides, consoles
    "midnight-grid": ["storage", "ssd", "hardware", "spec", "gb", "tb", "ps5", "xbox", "console", "install", "gigabytes", "megabytes", "drive"],
    "explainer-diagram": ["how to", "step", "guide", "tutorial", "process", "workflow", "method", "prerequisite", "instructions"],
    "blueprint": ["blueprint", "architecture", "dimensions", "chassis", "board", "schematic", "measurements"],
    "swiss-kinetic": ["fast", "quick", "versus", "vs", "editions", "compare", "comparison", "price", "standard", "ultimate", "countdown"],
    "data-story": ["statistics", "numbers", "sales", "revenue", "players", "metrics", "chart", "graph"],
    "editor-ui": ["code", "software", "development", "settings", "firmware", "system software", "interface"],
    "graphite-ui": ["minimal", "luxury", "dark", "sleek", "modern", "refined"],
    "motion-app-ui": ["app", "ui", "screen", "mobile", "ios", "android", "navigation"],
    "poster-pop": ["entertainment", "hype", "trailer", "release", "leak", "rumor", "news"],
    
    # Lemo specialized styles
    "lemo/exploded-teardown": ["teardown", "parts", "components", "heatsink", "fan", "cover", "m.2"],
    "lemo/dark-tech-keynote": ["keynote", "announcement", "reveal", "rockstar", "official", "event"],
    "lemo/satellite-briefing": ["map", "vice city", "location", "satellite", "leonida", "geography", "radar"],
    "lemo/engineering-briefing": ["telemetry", "diagnostic", "benchmark", "fps", "performance", "resolution"]
}

def analyze_script(script_text):
    text_lower = script_text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    
    scores = {}
    for style, keywords in STYLE_KEYWORDS.items():
        score = sum(text_lower.count(kw) * (2 if len(kw) > 4 else 1) for kw in keywords)
        scores[style] = score
        
    best_style = max(scores, key=scores.get)
    if scores[best_style] == 0:
        # Default fallback for general gaming / tech tutorials
        best_style = "midnight-grid"
        
    return best_style, scores

def get_style_metadata(style_id):
    if style_id.startswith("lemo/"):
        slug = style_id.split("/", 1)[1]
        style_path = LEMO_STYLES_DIR / slug / "STYLE.md"
    else:
        style_path = CLAUDE_STYLES_DIR / style_id / "STYLE.md"
        
    meta = {
        "style_id": style_id,
        "path": str(style_path),
        "exists": style_path.exists(),
        "palette": [],
        "type": [],
        "signature_moves": []
    }
    
    if style_path.exists():
        content = style_path.read_text(encoding="utf-8")
        # Extract palette colors
        palette_match = re.search(r'## Palette.*?\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
        if palette_match:
            meta["palette"] = [line.strip("- ") for line in palette_match.group(1).strip().splitlines() if line.strip()]
            
        # Extract motion/easing
        motion_match = re.search(r'## (?:Motion|Signature moves).*?\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
        if motion_match:
            meta["motion"] = [line.strip("- ") for line in motion_match.group(1).strip().splitlines() if line.strip()]
            
    return meta

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 select_style.py <path_to_script.md or text>")
        sys.exit(1)
        
    arg = sys.argv[1]
    if os.path.exists(arg):
        with open(arg, "r", encoding="utf-8") as f:
            script_text = f.read()
    else:
        script_text = arg
        
    best_style, scores = analyze_script(script_text)
    meta = get_style_metadata(best_style)
    
    result = {
        "selected_style": best_style,
        "confidence_score": scores.get(best_style, 0),
        "runner_up": sorted(scores.items(), key=lambda x: x[1], reverse=True)[1][0] if len(scores) > 1 else None,
        "metadata": meta
    }
    
    print(json.dumps(result, indent=2))
    return result

if __name__ == "__main__":
    main()
