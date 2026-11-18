#!/usr/bin/env python3
"""
Automated Style Selector & Catalog Indexer for CreatorRadar Studio.
Dynamically indexes the full catalog of:
1. Claude Video 2.0 Motion Graphics (styles/<id>/)
2. Lemo-Opuscar Code Films (styles/lemo/<id>/)
Extracts authentic palette hex codes, typography, mood, and motion rules so
downstream renderers and the Studio UI use real style tokens.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

STUDIO_ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parent.parent))
CLAUDE_STYLES_DIR = STUDIO_ROOT / "styles"
LEMO_STYLES_DIR = STUDIO_ROOT / "styles" / "lemo"

HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")

# Weighted domain keywords matched against verified style IDs on disk
STYLE_KEYWORDS: dict[str, list[str]] = {
    # Claude Video 2.0 styles
    "midnight-grid": [
        "storage", "ssd", "nvme", "hardware", "spec", "gb", "tb", "ps5", "xbox",
        "console", "install", "gigabytes", "megabytes", "drive", "system", "network", "ai",
    ],
    "explainer-diagram": [
        "how to", "step", "guide", "tutorial", "process", "workflow", "method",
        "prerequisite", "instructions", "setup", "preload", "survival",
    ],
    "blueprint": [
        "blueprint", "architecture", "dimensions", "chassis", "board", "schematic",
        "measurements", "engineering", "build",
    ],
    "swiss-kinetic": [
        "fast", "quick", "versus", "vs", "editions", "compare", "comparison",
        "price", "standard", "ultimate", "countdown", "rank", "top",
    ],
    "data-story": [
        "statistics", "numbers", "sales", "revenue", "players", "metrics",
        "chart", "graph", "million", "billion", "growth", "retention",
    ],
    "editor-ui": [
        "code", "software", "development", "settings", "firmware", "api",
        "python", "javascript", "terminal", "cli", "repo",
    ],
    "graphite-ui": ["minimal", "luxury", "dark", "sleek", "modern", "refined", "apple", "pro"],
    "motion-app-ui": ["app", "ui", "screen", "mobile", "ios", "android", "navigation", "dashboard"],
    "poster-pop": ["entertainment", "hype", "trailer", "release", "launch", "news", "breaking", "event"],
    "editorial-paper": ["essay", "deep dive", "history", "journalism", "vox", "explainer", "story", "culture"],
    "risograph": ["indie", "retro", "art", "music", "design", "zine", "creative"],
    "swiss-grid": ["checklist", "rules", "framework", "matrix", "breakdown", "audit"],
    "time-travel": ["timeline", "evolution", "years", "decade", "past", "future", "era"],
    "growing-city": ["city", "map", "world", "economy", "urban", "vice city", "leonida"],
    "particle-field": ["physics", "quantum", "space", "neural", "simulation", "particles"],
    "paper-cut": ["craft", "fable", "myth", "folklore", "animated story"],

    # Verified Lemo-Opuscar styles (matching actual folder names in styles/lemo/)
    "lemo/teardown": ["teardown", "parts", "components", "heatsink", "fan", "cover", "m.2", "pcb", "inside"],
    "lemo/dark-keynote": ["keynote", "announcement", "reveal", "rockstar", "official", "showcase"],
    "lemo/satellite-briefing": ["satellite", "geography", "radar", "terrain", "coordinates", "region"],
    "lemo/briefing-board": ["telemetry", "diagnostic", "benchmark", "fps", "performance", "resolution", "dossier"],
    "lemo/dark-documentary": ["investigation", "documentary", "mystery", "behind", "truth", "secret"],
    "lemo/circuit-board": ["chip", "gpu", "cpu", "silicon", "transistor", "cuda", "nvidia"],
    "lemo/news-package": ["breaking", "update", "patch", "report", "headline"],
    "lemo/hologram-hud": ["cyber", "sci-fi", "hud", "telemetry", "futuristic", "combat"],
    "lemo/visual-investigation": ["forensic", "evidence", "proof", "fact check", "verified", "source"],
}

DEFAULT_TOKENS = {
    "bg": "#0B1220",
    "surface": "#111A2E",
    "border": "#22304D",
    "text": "#E8EDF7",
    "muted": "#8C98B3",
    "accent": "#3D8BFF",
    "accent2": "#F47750",
}


def _hex_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _hex_saturation(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    return 0.0 if mx == 0 else (mx - mn) / mx


def _derive_tokens(palette_lines: list[str], raw_content: str) -> dict[str, str]:
    tokens = dict(DEFAULT_TOKENS)
    labeled: dict[str, str] = {}
    all_hexes: list[str] = []

    for line in palette_lines:
        hexes = HEX_RE.findall(line)
        all_hexes.extend(hexes)
        lower = line.lower()
        if not hexes:
            continue
        if any(k in lower for k in ("ground", "background", "bg", "canvas", "paper")):
            labeled.setdefault("bg", hexes[0])
        elif any(k in lower for k in ("panel", "card", "surface", "box")):
            labeled.setdefault("surface", hexes[0])
            if len(hexes) > 1:
                labeled.setdefault("border", hexes[1])
        elif any(k in lower for k in ("border", "grid", "dot", "wire", "rule", "line")):
            labeled.setdefault("border", hexes[0])
        elif any(k in lower for k in ("muted", "secondary", "sub")):
            labeled.setdefault("muted", hexes[0])
        elif any(k in lower for k in ("ink", "text", "foreground")):
            labeled.setdefault("text", hexes[0])
        elif any(k in lower for k in ("accent", "highlight", "red", "blue", "orange", "primary")):
            if "accent" not in labeled:
                labeled["accent"] = hexes[0]
            elif "accent2" not in labeled:
                labeled["accent2"] = hexes[0]

    if not all_hexes:
        all_hexes = HEX_RE.findall(raw_content)

    # Deduplicate preserving order
    unique_hexes = list(dict.fromkeys(h.upper() for h in all_hexes))

    if labeled:
        tokens.update({k: v.upper() for k, v in labeled.items()})
    elif unique_hexes:
        # Infer dark/light ground & brightest saturated accent
        sorted_by_lum = sorted(unique_hexes, key=_hex_luminance)
        tokens["bg"] = sorted_by_lum[0]
        tokens["text"] = sorted_by_lum[-1]
        sat_candidates = sorted(unique_hexes, key=_hex_saturation, reverse=True)
        if sat_candidates and _hex_saturation(sat_candidates[0]) > 0.25:
            tokens["accent"] = sat_candidates[0]
            if len(sat_candidates) > 1 and _hex_saturation(sat_candidates[1]) > 0.2:
                tokens["accent2"] = sat_candidates[1]

    # Ensure readable contrast between bg and text
    bg_lum = _hex_luminance(tokens["bg"])
    txt_lum = _hex_luminance(tokens["text"])
    if abs(bg_lum - txt_lum) < 0.35:
        if bg_lum < 0.45:
            tokens["text"] = "#F1F5F9"
            tokens["muted"] = "#94A3B8"
            if "surface" not in labeled:
                tokens["surface"] = "#152036"
                tokens["border"] = "#263656"
        else:
            tokens["text"] = "#111827"
            tokens["muted"] = "#4B5563"
            if "surface" not in labeled:
                tokens["surface"] = "#FFFFFF"
                tokens["border"] = "#D1D5DB"

    return tokens


def get_style_metadata(style_id: str) -> dict:
    if style_id.startswith("lemo/"):
        slug = style_id.split("/", 1)[1]
        style_dir = LEMO_STYLES_DIR / slug
        catalog = "lemo-opuscar"
    else:
        slug = style_id
        style_dir = CLAUDE_STYLES_DIR / slug
        catalog = "claude-video"

    style_path = style_dir / "STYLE.md"
    template_html = style_dir / "index.html"

    pretty_name = slug.replace("-", " ").title()
    meta: dict = {
        "style_id": style_id,
        "name": pretty_name,
        "catalog": catalog,
        "path": str(style_path),
        "exists": style_path.exists(),
        "has_template": template_html.exists(),
        "template_path": str(template_html) if template_html.exists() else None,
        "best_for": "",
        "mood": "",
        "palette": [],
        "hex_colors": [],
        "tokens": dict(DEFAULT_TOKENS),
        "type": [],
        "motion": [],
        "signature_moves": [],
    }

    if not style_path.exists():
        return meta

    content = style_path.read_text(encoding="utf-8", errors="replace")

    h1 = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if h1:
        name = re.sub(r"\s*[—–-]\s*Style Prompt.*$", "", h1.group(1).strip(), flags=re.I)
        meta["name"] = name.strip()

    best_for = re.search(r"^Best for:\s*(.+)$", content, re.MULTILINE | re.I)
    if best_for:
        meta["best_for"] = best_for.group(1).strip()

    mood = re.search(r"^Mood:\s*(.+)$", content, re.MULTILINE | re.I)
    if mood:
        meta["mood"] = mood.group(1).strip()
    elif not meta["best_for"]:
        # Grab first blockquote summary in Lemo STYLE.md files
        bq = re.search(r"^>\s*(.+)$", content, re.MULTILINE)
        if bq:
            meta["mood"] = bq.group(1).strip()[:220]

    palette_match = re.search(r"##\s+(?:\d+\.\s*)?(?:Palette|Colou?r\s+logic).*?\n(.*?)(?=\n##\s|\Z)", content, re.DOTALL | re.I)
    if palette_match:
        lines = [line.strip().lstrip("-• ").strip() for line in palette_match.group(1).strip().splitlines() if line.strip()]
        meta["palette"] = lines[:8]

    type_match = re.search(r"##\s+(?:\d+\.\s*)?Type.*?\n(.*?)(?=\n##\s|\Z)", content, re.DOTALL | re.I)
    if type_match:
        meta["type"] = [line.strip().lstrip("-• ").strip() for line in type_match.group(1).strip().splitlines() if line.strip()][:6]

    motion_match = re.search(r"##\s+(?:\d+\.\s*)?(?:Motion(?:\s+rules|\s+quality)?|Easing).*?\n(.*?)(?=\n##\s|\Z)", content, re.DOTALL | re.I)
    if motion_match:
        meta["motion"] = [line.strip().lstrip("-• ").strip() for line in motion_match.group(1).strip().splitlines() if line.strip()][:6]

    sig_match = re.search(r"##\s+(?:\d+\.\s*)?(?:Signature moves|Native moves).*?\n(.*?)(?=\n##\s|\Z)", content, re.DOTALL | re.I)
    if sig_match:
        meta["signature_moves"] = [line.strip().lstrip("-• ").strip() for line in sig_match.group(1).strip().splitlines() if line.strip()][:6]

    meta["tokens"] = _derive_tokens(meta["palette"], content)
    raw_hexes = HEX_RE.findall("\n".join(meta["palette"]) + "\n" + content[:2500])
    meta["hex_colors"] = list(dict.fromkeys(h.upper() for h in raw_hexes))[:6]
    return meta


def list_all_styles() -> list[dict]:
    styles: list[dict] = []
    if CLAUDE_STYLES_DIR.exists():
        for d in sorted(CLAUDE_STYLES_DIR.iterdir()):
            if d.is_dir() and d.name != "lemo" and (d / "STYLE.md").exists():
                styles.append(get_style_metadata(d.name))
    if LEMO_STYLES_DIR.exists():
        for d in sorted(LEMO_STYLES_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith("_") and (d / "STYLE.md").exists():
                styles.append(get_style_metadata(f"lemo/{d.name}"))
    return styles


def analyze_script(script_text: str) -> tuple[str, dict[str, int]]:
    text_lower = script_text.lower()
    scores: dict[str, int] = {}

    for style, keywords in STYLE_KEYWORDS.items():
        score = 0
        for kw in keywords:
            count = len(re.findall(r"\b" + re.escape(kw) + r"\b", text_lower))
            if count:
                score += count * (2 if len(kw) > 4 else 1)
        scores[style] = score

    # Also lightly score any discovered style whose slug tokens appear in the text
    for style_dir_base, prefix in ((CLAUDE_STYLES_DIR, ""), (LEMO_STYLES_DIR, "lemo/")):
        if not style_dir_base.exists():
            continue
        for d in style_dir_base.iterdir():
            if not d.is_dir() or d.name in ("lemo", "_template") or not (d / "STYLE.md").exists():
                continue
            sid = f"{prefix}{d.name}"
            if sid in scores:
                continue
            slug_words = [w for w in d.name.split("-") if len(w) > 3]
            s = sum(len(re.findall(r"\b" + re.escape(w) + r"\b", text_lower)) * 2 for w in slug_words)
            if s > 0:
                scores[sid] = s

    best_style = max(scores, key=scores.get) if scores else "midnight-grid"
    if scores.get(best_style, 0) == 0:
        best_style = "midnight-grid"

    return best_style, scores


def select_style(script_text: str, preferred_style: str | None = None) -> dict:
    if preferred_style and preferred_style != "auto":
        meta = get_style_metadata(preferred_style)
        if meta["exists"]:
            return {
                "selected_style": preferred_style,
                "confidence_score": 100,
                "runner_up": None,
                "selection_mode": "manual",
                "metadata": meta,
            }

    best_style, scores = analyze_script(script_text)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    runner_up = ranked[1][0] if len(ranked) > 1 else None
    meta = get_style_metadata(best_style)

    return {
        "selected_style": best_style,
        "confidence_score": scores.get(best_style, 0),
        "runner_up": runner_up,
        "selection_mode": "auto",
        "metadata": meta,
    }


def main():
    parser = argparse.ArgumentParser(description="CreatorRadar Style Selector & Catalog")
    parser.add_argument("input", nargs="?", help="Path to script.md or raw topic/script text")
    parser.add_argument("--list", action="store_true", help="List all available styles as JSON")
    parser.add_argument("--style", default=None, help="Force a specific style ID and print its metadata")
    args = parser.parse_args()

    if args.list:
        catalog = list_all_styles()
        print(json.dumps({"count": len(catalog), "styles": catalog}, indent=2))
        return

    if args.style:
        result = select_style("", preferred_style=args.style)
        print(json.dumps(result, indent=2))
        return

    if not args.input:
        parser.print_help()
        sys.exit(1)

    if os.path.exists(args.input):
        script_text = Path(args.input).read_text(encoding="utf-8")
    else:
        script_text = args.input

    result = select_style(script_text)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
