#!/usr/bin/env python3
"""
CreatorRadar YouTube Data API v3 OAuth & Automated Uploader

Features:
- Google OAuth 2.0 login (supports both Desktop App & Web App client_secret.json)
- Persistent refresh token saved securely in config/youtube_token.json (chmod 600)
- Smart YouTube SEO engine: auto-generates Titles, #Shorts detection, Hashtags,
  500-char-safe Tags, Category ID, Chapters, Official Sources, and mandatory Rule 5 AI Disclosure
- Chunked resumable video upload (4 MB chunks) with live progress callbacks & retries
- Optional custom thumbnail upload & scheduled publishAt support
- Rule 4 human approval gate enforcement (default safe privacy = private drafts unless approved)
- Standalone CLI (--auth, --status, --preview, --upload) AND Dashboard API integration
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable

STUDIO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = STUDIO_ROOT / "config"
EXPORTS_DIR = STUDIO_ROOT / "exports"
LIVE_CLIPS_DIR = EXPORTS_DIR / "live-clips"

CLIENT_SECRET_PATH = CONFIG_DIR / "youtube_client_secret.json"
TOKEN_PATH = CONFIG_DIR / "youtube_token.json"
UPLOAD_HISTORY_PATH = CONFIG_DIR / "youtube_upload_history.json"

PROFILE_LABELS = {
    "studio": "Main Studio Channel",
    "clipper": "Live Clipper Channel",
}
VALID_PROFILES = tuple(PROFILE_LABELS.keys())


def normalize_profile(profile: str | None = None, kind: str | None = None) -> str:
    """Normalize a YouTube channel profile slot ('studio' or 'clipper')."""
    if profile:
        p = str(profile).strip().lower()
        if p in ("clipper", "clip", "clips", "live", "live-clipper"):
            return "clipper"
        if p in ("studio", "main", "default"):
            return "studio"
    if kind == "clip":
        return "clipper"
    return "studio"


def get_token_path(profile: str | None = "studio") -> Path:
    prof = normalize_profile(profile)
    if prof == "clipper":
        return CONFIG_DIR / "youtube_token_clipper.json"
    return TOKEN_PATH


def get_client_secret_save_path(profile: str | None = "studio") -> Path:
    prof = normalize_profile(profile)
    if prof == "clipper":
        return CONFIG_DIR / "youtube_client_secret_clipper.json"
    return CLIENT_SECRET_PATH

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    # Required by scripts/publish_agent.py to flip private->public (videos.update)
    # and to delete rejected clips (videos.delete). Tokens granted before this was
    # added do not carry it: re-run `--auth --profile <p>` once to re-consent.
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

# Raised when a stored token predates the force-ssl scope and the API rejects a
# manage call. Carries the exact re-auth command the operator has to run.
class YouTubeScopeError(RuntimeError):
    """Stored OAuth token is missing youtube.force-ssl; re-auth is required."""


def _manage_scope_hint(profile: str) -> str:
    prof = normalize_profile(profile)
    return (
        "YouTube rejected this call because the saved token predates the "
        "youtube.force-ssl scope. Re-consent once:\n"
        f"    .venv/bin/python scripts/youtube_uploader.py --auth --profile {prof}\n"
        "(open the printed URL, approve, then retry)"
    )

AI_DISCLOSURE_STUDIO = (
    "Graphics created with AI assistance. All facts sourced from official documentation."
)
AI_DISCLOSURE_CLIP = (
    "Graphics and automated captions created with AI assistance. "
    "All facts sourced from official documentation."
)

YOUTUBE_CATEGORIES = {
    "20": "Gaming",
    "24": "Entertainment",
    "28": "Science & Technology",
    "22": "People & Blogs",
    "27": "Education",
    "25": "News & Politics",
    "1": "Film & Animation",
}

DEFAULT_CALLBACK_PORT = int(os.environ.get("STUDIO_UI_PORT", "3000"))
DEFAULT_DASHBOARD_REDIRECT_URI = f"http://localhost:{DEFAULT_CALLBACK_PORT}/api/youtube/oauth/callback"

# In-memory pending OAuth flows keyed by state (preserves PKCE code_verifier)
_PENDING_OAUTH: dict[str, dict[str, Any]] = {}
_PENDING_LOCK = threading.Lock()


def _lazy_google_imports():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
        return Request, Credentials, Flow, build, HttpError, MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "YouTube API libraries not installed. Run: "
            "uv pip install --python .venv/bin/python google-api-python-client google-auth-oauthlib google-auth-httplib2"
        ) from exc


def find_client_secret_path(profile: str | None = "studio") -> Path | None:
    """Locate client_secret.json (profile-specific first, then shared config/ or repo root)."""
    prof = normalize_profile(profile)
    if prof == "clipper":
        clipper_secret = CONFIG_DIR / "youtube_client_secret_clipper.json"
        if clipper_secret.exists():
            return clipper_secret
    if CLIENT_SECRET_PATH.exists():
        return CLIENT_SECRET_PATH
    for folder in (CONFIG_DIR, STUDIO_ROOT):
        if not folder.exists():
            continue
        candidates = sorted(folder.glob("client_secret*.json"))
        if candidates:
            return candidates[0]
    return None


def load_client_secret_info(profile: str | None = "studio") -> dict[str, Any]:
    path = find_client_secret_path(profile=profile)
    if not path:
        return {
            "exists": False,
            "path": None,
            "client_type": None,
            "client_id_preview": None,
            "project_id": None,
            "redirect_uris": [],
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        client_type = "installed" if "installed" in raw else ("web" if "web" in raw else None)
        section = raw.get(client_type, {}) if client_type else {}
        cid = section.get("client_id", "")
        preview = f"{cid[:16]}...{cid[-18:]}" if len(cid) > 36 else cid
        return {
            "exists": True,
            "path": str(path),
            "client_type": client_type,
            "client_id_preview": preview,
            "project_id": section.get("project_id"),
            "redirect_uris": section.get("redirect_uris") or [],
        }
    except Exception as exc:
        return {
            "exists": False,
            "path": str(path),
            "error": str(exc),
            "client_type": None,
            "client_id_preview": None,
            "project_id": None,
            "redirect_uris": [],
        }


def save_client_secret(payload: dict[str, Any] | str, profile: str | None = None) -> dict[str, Any]:
    """
    Save Google Cloud OAuth 2.0 client secret JSON to config/youtube_client_secret.json
    (or config/youtube_client_secret_clipper.json when profile='clipper').
    Accepts either:
      - Full Google Cloud downloaded JSON (string or dict with 'installed' or 'web')
      - Direct dict with {'client_id': '...', 'client_secret': '...', 'project_id'?: '...'}
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        data = json.loads(payload)
    else:
        data = dict(payload)

    target_profile = normalize_profile(profile or data.get("profile")) if (profile or data.get("profile")) else "studio"
    save_path = get_client_secret_save_path(target_profile)

    if "raw_json" in data and isinstance(data["raw_json"], str) and data["raw_json"].strip():
        data = json.loads(data["raw_json"])

    if "installed" in data or "web" in data:
        key = "installed" if "installed" in data else "web"
        sec = data[key]
        if not sec.get("client_id") or not sec.get("client_secret"):
            raise ValueError(f"Invalid client secret JSON: missing client_id or client_secret inside '{key}'.")
        normalized = data
    elif data.get("client_id") and data.get("client_secret"):
        client_type = "web" if data.get("client_type") == "web" else "installed"
        redirect_uris = data.get("redirect_uris") or [
            DEFAULT_DASHBOARD_REDIRECT_URI,
            "http://localhost",
        ]
        normalized = {
            client_type: {
                "client_id": str(data["client_id"]).strip(),
                "project_id": str(data.get("project_id") or "creatorradar-youtube").strip(),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": str(data["client_secret"]).strip(),
                "redirect_uris": redirect_uris,
            }
        }
    else:
        raise ValueError(
            "Provide either the full Google Cloud client_secret.json content "
            "or both 'client_id' and 'client_secret'."
        )

    save_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    try:
        os.chmod(save_path, 0o600)
    except OSError:
        pass
    return load_client_secret_info(profile=target_profile)


def pick_redirect_uri(preferred: str = DEFAULT_DASHBOARD_REDIRECT_URI, profile: str | None = "studio") -> str:
    """
    Choose the best redirect URI compatible with the saved client_secret.json.
    - Desktop App ('installed') supports any http://localhost:<port>/<path>
    - Web App ('web') must exactly match one of the configured redirect_uris
    """
    info = load_client_secret_info(profile=profile)
    if info.get("client_type") == "web":
        uris = info.get("redirect_uris") or []
        if preferred in uris:
            return preferred
        for u in uris:
            if "localhost:8080" in u or "127.0.0.1:8080" in u or "localhost:3000" in u:
                return u
        if uris:
            return uris[0]
    return preferred


def build_oauth_url(redirect_uri: str | None = None, profile: str | None = "studio") -> dict[str, Any]:
    """Generate a Google OAuth 2.0 authorization URL for a profile ('studio' or 'clipper')."""
    _, _, Flow, _, _, _ = _lazy_google_imports()
    prof = normalize_profile(profile)
    secret_path = find_client_secret_path(profile=prof)
    if not secret_path:
        raise FileNotFoundError(
            f"Google Cloud OAuth client secret not found. Place your downloaded client_secret.json "
            f"at {CLIENT_SECRET_PATH} or upload it in the Studio Dashboard."
        )

    chosen_redirect = pick_redirect_uri(redirect_uri or DEFAULT_DASHBOARD_REDIRECT_URI, profile=prof)
    flow = Flow.from_client_secrets_file(
        str(secret_path),
        scopes=SCOPES,
        redirect_uri=chosen_redirect,
    )
    # Prefix state with profile so callback routes to the exact token slot even across restarts
    state = f"{prof}.{secrets.token_urlsafe(24)}"
    auth_url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
        state=state,
    )

    # Prune stale pending flows older than 20 min
    now = time.time()
    with _PENDING_LOCK:
        for k in [k for k, v in _PENDING_OAUTH.items() if now - v["created_at"] > 1200]:
            _PENDING_OAUTH.pop(k, None)
        _PENDING_OAUTH[returned_state] = {
            "flow": flow,
            "redirect_uri": chosen_redirect,
            "profile": prof,
            "created_at": now,
        }

    return {
        "auth_url": auth_url,
        "state": returned_state,
        "redirect_uri": chosen_redirect,
        "profile": prof,
        "profile_label": PROFILE_LABELS[prof],
    }


def _fetch_channel_profile(creds) -> dict[str, Any]:
    _, _, _, build, _, _ = _lazy_google_imports()
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    items = resp.get("items") or []
    if not items:
        return {
            "id": None,
            "title": "Google Account (No YouTube Channel Found)",
            "custom_url": None,
            "subscribers": 0,
            "video_count": 0,
            "thumbnail_url": None,
        }
    ch = items[0]
    snip = ch.get("snippet") or {}
    stats = ch.get("statistics") or {}
    thumbs = snip.get("thumbnails") or {}
    thumb = (thumbs.get("medium") or thumbs.get("default") or {}).get("url")
    return {
        "id": ch.get("id"),
        "title": snip.get("title") or "Connected YouTube Channel",
        "custom_url": snip.get("customUrl"),
        "subscribers": int(stats.get("subscriberCount") or 0),
        "video_count": int(stats.get("videoCount") or 0),
        "view_count": int(stats.get("viewCount") or 0),
        "thumbnail_url": thumb,
    }


def _save_token_bundle(
    creds,
    channel_info: dict[str, Any] | None = None,
    profile: str | None = "studio",
) -> dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    prof = normalize_profile(profile)
    token_path = get_token_path(prof)
    existing_channel = None
    if token_path.exists():
        try:
            existing = json.loads(token_path.read_text(encoding="utf-8"))
            existing_channel = existing.get("channel")
        except Exception:
            pass
    bundle = {
        "profile": prof,
        "oauth": json.loads(creds.to_json()),
        "channel": channel_info or existing_channel,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    token_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass
    return bundle


def _profile_from_state(state: str | None) -> str | None:
    if not state or "." not in state:
        return None
    prefix = state.split(".", 1)[0].strip().lower()
    if prefix in VALID_PROFILES:
        return prefix
    return None


def complete_oauth_callback(
    code: str,
    state: str | None = None,
    redirect_uri: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Exchange OAuth authorization code for persistent tokens and fetch channel profile."""
    _, _, Flow, _, _, _ = _lazy_google_imports()
    flow = None
    entry_profile = None
    with _PENDING_LOCK:
        if state and state in _PENDING_OAUTH:
            entry = _PENDING_OAUTH.pop(state)
            flow = entry["flow"]
            entry_profile = entry.get("profile")

    resolved_profile = normalize_profile(profile or entry_profile or _profile_from_state(state) or "studio")

    if flow is None:
        secret_path = find_client_secret_path(profile=resolved_profile)
        if not secret_path:
            raise FileNotFoundError("Client secret missing during OAuth callback.")
        flow = Flow.from_client_secrets_file(
            str(secret_path),
            scopes=SCOPES,
            redirect_uri=pick_redirect_uri(redirect_uri or DEFAULT_DASHBOARD_REDIRECT_URI, profile=resolved_profile),
        )

    # Allow Google returning superset/reordered scopes without throwing
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    flow.fetch_token(code=code)
    creds = flow.credentials
    channel = _fetch_channel_profile(creds)
    _save_token_bundle(creds, channel, profile=resolved_profile)
    return {
        "connected": True,
        "profile": resolved_profile,
        "profile_label": PROFILE_LABELS[resolved_profile],
        "token_path": str(get_token_path(resolved_profile)),
        "channel": channel,
    }


def load_credentials(refresh_if_needed: bool = True, profile: str | None = "studio"):
    """Load saved OAuth credentials for a profile and refresh automatically if expired."""
    Request, Credentials, _, _, _, _ = _lazy_google_imports()
    prof = normalize_profile(profile)
    token_path = get_token_path(prof)
    if not token_path.exists():
        return None, None
    try:
        raw = json.loads(token_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None

    oauth_info = raw.get("oauth") if isinstance(raw, dict) and "oauth" in raw else raw
    channel_info = raw.get("channel") if isinstance(raw, dict) else None
    creds = Credentials.from_authorized_user_info(oauth_info, scopes=SCOPES)

    if refresh_if_needed and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token_bundle(creds, channel_info, profile=prof)

    return creds, channel_info


def disconnect_youtube(profile: str | None = "studio") -> dict[str, Any]:
    prof = normalize_profile(profile)
    token_path = get_token_path(prof)
    if token_path.exists():
        token_path.unlink()
    return {"connected": False, "disconnected": True, "profile": prof}


def get_profile_status(profile: str | None = "studio", refresh_channel: bool = False) -> dict[str, Any]:
    prof = normalize_profile(profile)
    token_path = get_token_path(prof)
    connected = False
    has_refresh_token = False
    channel = None
    token_error = None

    if token_path.exists():
        try:
            creds, channel = load_credentials(refresh_if_needed=True, profile=prof)
            if creds and creds.valid:
                connected = True
                has_refresh_token = bool(creds.refresh_token)
                if refresh_channel or not channel:
                    channel = _fetch_channel_profile(creds)
                    _save_token_bundle(creds, channel, profile=prof)
        except Exception as exc:
            token_error = str(exc)

    return {
        "profile": prof,
        "label": PROFILE_LABELS[prof],
        "connected": connected,
        "has_refresh_token": has_refresh_token,
        "channel": channel,
        "token_path": str(token_path) if token_path.exists() else None,
        "error": token_error,
    }


def get_youtube_status(refresh_channel: bool = False, profile: str | None = "studio") -> dict[str, Any]:
    prof = normalize_profile(profile)
    secret_info = load_client_secret_info(profile=prof)
    profiles = {
        p: get_profile_status(profile=p, refresh_channel=refresh_channel)
        for p in VALID_PROFILES
    }
    primary = profiles[prof]

    return {
        "profile": prof,
        "has_client_secret": secret_info["exists"],
        "client_secret_path": secret_info["path"],
        "client_type": secret_info["client_type"],
        "client_id_preview": secret_info["client_id_preview"],
        "project_id": secret_info["project_id"],
        "redirect_uri": pick_redirect_uri(DEFAULT_DASHBOARD_REDIRECT_URI, profile=prof),
        "connected": primary["connected"],
        "has_refresh_token": primary["has_refresh_token"],
        "channel": primary["channel"],
        "token_path": primary["token_path"],
        "error": primary["error"],
        "profiles": profiles,
        "categories": YOUTUBE_CATEGORIES,
    }


def probe_video_info(video_path: Path) -> dict[str, Any]:
    """Read width, height, and duration of an MP4 using ffprobe."""
    info = {"width": 1080, "height": 1920, "duration": 0.0, "is_short": True}
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height:format=duration",
                "-of", "json",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=8,
        )
        if res.returncode == 0:
            data = json.loads(res.stdout)
            streams = data.get("streams") or []
            if streams:
                info["width"] = int(streams[0].get("width") or 1080)
                info["height"] = int(streams[0].get("height") or 1920)
            dur = float((data.get("format") or {}).get("duration") or 0.0)
            info["duration"] = round(dur, 2)
            info["is_short"] = (info["height"] >= info["width"]) and (dur <= 180.0)
    except Exception:
        pass
    return info


def _clean_hashtag(word: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", word)
    return f"#{cleaned}" if cleaned else ""


def _generate_smart_hashtags_and_tags(
    title: str,
    context_text: str,
    is_short: bool,
    is_live_clip: bool = False,
    channel_slug: str = "",
    extra_tags: list[str] | None = None,
    streamer_name: str = "",
    game_name: str = "",
    platform_name: str = "",
) -> tuple[list[str], list[str]]:
    """
    Generate YouTube-compliant hashtags (4-6 optimal) and SEO tags (<= 480 chars total).
    Covers exact-match, broad, and long-tail tiers per skills/youtube-seo/SKILL.md.
    """
    haystack = f"{title} {context_text} {channel_slug} {streamer_name} {game_name}".lower()

    hashtags: list[str] = []
    tags: list[str] = []

    def add_ht(h: str):
        tag = h if h.startswith("#") else f"#{h}"
        tag = _clean_hashtag(tag)
        if tag and tag.lower() not in {x.lower() for x in hashtags}:
            hashtags.append(tag)

    def add_tag(t: str):
        t = re.sub(r"\s+", " ", t).strip().strip("#")
        if not t or len(t) < 2 or len(t) > 60:
            return
        if t.lower() not in {x.lower() for x in tags}:
            tags.append(t)

    # Strip boilerplate AI disclosure before checking topic keywords so gaming videos aren't tagged #AI
    clean_haystack = re.sub(r"graphics[^.\n]*ai assistance\.?", "", haystack, flags=re.I)
    clean_haystack = re.sub(r"all facts sourced from official documentation\.?", "", clean_haystack, flags=re.I)

    # Topic / Pillar Detection
    is_gta = any(k in clean_haystack for k in ("gta 6", "gta vi", "gtavi", "gta6", "vice city", "leonida", "lucia", "jason", "rockstar"))
    is_gaming = is_gta or is_live_clip or any(k in clean_haystack for k in ("ps5", "xbox", "gameplay", "stream", "gaming", "clutch", "valorant", "minecraft", "bgmi", "esports"))
    is_ai_tech = (not is_live_clip) and any(k in clean_haystack for k in ("artificial intelligence", "llm", "chatgpt", "gemini", "claude", "coding", "python", "ai agent", "ai tool", "tech explainer"))
    is_indian_gaming = any(
        k in clean_haystack
        for k in (
            "mythpat", "triggered", "live insaan", "scout", "mortal", "jonathan",
            "techno", "ujjwal", "beastboyshub", "bbs", "total gaming", "ajju",
            "gamerfleet", "rakazone", "payal", "carryminati", "carry", "bhai",
            "arey", "hindi", "hinglish", "india",
        )
    )

    if is_short:
        add_ht("#Shorts")

    # For live clips, prioritize Streamer + Game + Clip-Specific keywords at the very top of hashtags & tags
    if is_live_clip:
        if streamer_name:
            streamer_ht = "#" + re.sub(r"[^A-Za-z0-9]", "", streamer_name)
            add_ht(streamer_ht)
            s_low = streamer_name.lower()
            if game_name:
                add_tag(f"{s_low} {game_name.lower()}")
            add_tag(s_low)
            add_tag(f"{s_low} live")
            add_tag(f"{s_low} clips")
            add_tag(f"{s_low} funny moments")
        elif channel_slug:
            parts = [p for p in re.split(r"[-_\s]+", channel_slug) if p and p.lower() not in ("gta6", "gtavi", "live", "stream", "clip")]
            if parts:
                creator_name = parts[0]
                add_ht(f"#{creator_name.capitalize()}")
                add_tag(creator_name.lower())
                add_tag(f"{creator_name.lower()} live")
                add_tag(f"{creator_name.lower()} clips")
                if is_gta:
                    add_tag(f"{creator_name.lower()} gta 6")

        if extra_tags:
            for t in extra_tags:
                add_tag(t)

        if is_gta:
            add_ht("#GTA6")
            add_ht("#GTAVI")
        elif game_name:
            add_ht("#" + re.sub(r"[^A-Za-z0-9]", "", game_name))

        if is_indian_gaming:
            add_ht("#IndianGaming")
        elif platform_name.lower() == "twitch":
            add_ht("#TwitchClips")
        else:
            add_ht("#GamingShorts" if is_short else "#LiveClips")

    if is_short:
        add_tag("shorts")
        add_tag("youtube shorts")

    if is_gta:
        add_ht("#GTAVI")
        add_ht("#GTA6")
        if not is_live_clip:
            add_ht("#RockstarGames")
        for t in (
            "gta 6", "gta vi", "gta 6 gameplay", "gta 6 live",
            "grand theft auto 6", "gta 6 shorts" if is_short else "gta 6 update",
            "vice city", "rockstar games", "gta 6 moments",
        ):
            add_tag(t)

    if (not is_live_clip) and channel_slug:
        parts = [p for p in re.split(r"[-_\s]+", channel_slug) if p and p.lower() not in ("gta6", "gtavi", "live", "stream", "clip")]
        if parts:
            creator_name = parts[0]
            add_ht(f"#{creator_name.capitalize()}")
            add_tag(creator_name.lower())
            add_tag(f"{creator_name.lower()} live")
            add_tag(f"{creator_name.lower()} clips")
            if is_gta:
                add_tag(f"{creator_name.lower()} gta 6")

    if is_live_clip:
        add_ht("#GamingShorts" if is_short else "#LiveClips")
        add_ht("#StreamHighlights")
        for t in ("live stream clips", "stream highlights", "viral gaming clips", "funny gaming moments", "gaming shorts"):
            add_tag(t)
        if platform_name.lower() == "twitch":
            add_tag("twitch clips")
        else:
            add_tag("youtube live clips")
        if any(k in clean_haystack for k in ("ishowspeed", "kai cenat", "kaicenat", "caseoh", "jynxzi", "adin", "xqc", "mrbeast")):
            add_ht("#ViralClips")
            for k, ht, tg in (
                ("ishowspeed", "#IShowSpeed", "ishowspeed clips"),
                ("kai cenat", "#KaiCenat", "kai cenat clips"),
                ("kaicenat", "#KaiCenat", "kai cenat clips"),
                ("caseoh", "#CaseOh", "caseoh clips"),
                ("jynxzi", "#Jynxzi", "jynxzi clips"),
            ):
                if k in clean_haystack:
                    add_ht(ht)
                    add_tag(tg)
                    add_tag(f"{k} gta 6" if is_gta else f"{k} funny moments")
        if is_indian_gaming:
            add_ht("#IndianGaming")
            add_tag("indian gaming")
            add_tag("indian gaming clips")
            add_tag("hindi gaming shorts")

    if is_gaming:
        add_ht("#Gaming")
        for t in ("gaming", "gaming shorts" if is_short else "gaming news", "ps5", "xbox series x"):
            add_tag(t)

    if is_ai_tech:
        add_ht("#AI")
        add_ht("#Tech")
        for t in ("artificial intelligence", "ai tools", "tech explainer", "ai workflow"):
            add_tag(t)

    # Keep hashtags to YouTube's sweet spot (max 6), always retaining the channel brand tag
    if is_live_clip:
        add_tag("clipsurge")
        add_tag("clipsurge shorts")
        hashtags = [h for h in hashtags if h.lower() != "#clipsurge"][:5] + ["#ClipSurge"]
    else:
        add_tag("creatorradar")
        hashtags = [h for h in hashtags if h.lower() != "#creatorradar"][:5] + ["#CreatorRadar"]

    # Enforce YouTube's strict 500-character total tag length limit (comma-separated + quotes buffer)
    final_tags: list[str] = []
    total_chars = 0
    for t in tags:
        cost = len(t) + (3 if " " in t else 1)
        if total_chars + cost > 460:
            break
        final_tags.append(t)
        total_chars += cost
        if len(final_tags) >= 24:
            break

    return hashtags, final_tags


_STREAMER_DISPLAY_MAP: dict[str, str] = {
    "ishowspeed": "IShowSpeed",
    "speed": "IShowSpeed",
    "mythpat": "Mythpat",
    "kaicenat": "Kai Cenat",
    "kai": "Kai Cenat",
    "xqc": "xQc",
    "caseoh": "CaseOh",
    "jynxzi": "Jynxzi",
    "triggeredinsaan": "Triggered Insaan",
    "liveinsaan": "Triggered Insaan",
    "carryminati": "CarryMinati",
    "carryislive": "CarryMinati",
    "technogamerz": "Techno Gamerz",
    "ujjwal": "Techno Gamerz",
    "beastboyshub": "BeastBoyShub",
    "bbs": "BeastBoyShub",
    "gamerfleet": "GamerFleet",
    "scout": "Sc0ut",
    "scoutop": "Sc0ut",
    "mortal": "MortaL",
    "totalgaming": "Total Gaming",
    "ajjubhai": "Total Gaming",
    "adinross": "Adin Ross",
    "adin": "Adin Ross",
    "pokimane": "Pokimane",
    "shroud": "Shroud",
    "tarik": "Tarik",
    "valkyrae": "Valkyrae",
    "mrbeast": "MrBeast",
    "rakazone": "RakaZone",
    "payalgaming": "Payal Gaming",
}

_GAME_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:gta\s*6|gta\s*vi|gtavi|gta6|vice\s*city|leonida)\b", "GTA 6"),
    (r"\b(?:gta\s*5|gta\s*v|gtav|gta5)\b", "GTA 5"),
    (r"\bvalorant\b", "Valorant"),
    (r"\bminecraft\b", "Minecraft"),
    (r"\b(?:bgmi|pubg)\b", "BGMI"),
    (r"\bfortnite\b", "Fortnite"),
    (r"\belden\s*ring\b", "Elden Ring"),
    (r"\b(?:ea\s*fc|fifa)\b", "EA FC"),
]

_PROFANITY_RE = re.compile(
    r"\b(?:f+u+c+k\w*|s+h+i+t\w*|b+i+t+c+h\w*|a+s+s+h+o+l+e\w*|m+o+t+h+e+r+f\w*|c+u+n+t\w*|d+i+c+k\w*|p+u+s+s+y\w*|n+i+g+g\w*|f+a+g+\w*|b+h+e+n+c+h+o+d\w*|m+a+d+a+r+c+h+o+d\w*|c+h+u+t+i+y+a\w*|b+s+d+k|m+c|b+c)\b",
    flags=re.I,
)


_CREATOR_PUBLIC_URLS: dict[str, str] = {
    "mythpat": "https://www.youtube.com/@Mythpat",
    "ishowspeed": "https://www.twitch.tv/ishowspeed",
    "kai cenat": "https://www.twitch.tv/kaicenat",
    "xqc": "https://www.twitch.tv/xqc",
    "caseoh": "https://www.twitch.tv/caseoh_",
    "jynxzi": "https://www.twitch.tv/jynxzi",
    "triggered insaan": "https://www.youtube.com/@LiveInsaan",
    "carryminati": "https://www.youtube.com/@CarryisLive",
    "techno gamerz": "https://www.youtube.com/@TechnoGamerzOfficial",
    "beastboyshub": "https://www.youtube.com/@BeastBoyShub",
    "gamerfleet": "https://www.youtube.com/@GamerFleet",
}

_LOCAL_PATH_RE = re.compile(
    r"(?:file://[^\s]+|/(?:home|Users|tmp|var|opt|mnt|etc|root)/[^\s]+|[A-Za-z]:\\[^\s]+)",
    flags=re.I,
)


def _sanitize_public_source_url(source_url: str, streamer: str = "", channel_slug: str = "") -> str:
    """Only allow real public https:// stream/channel URLs; NEVER leak local filesystem paths into YouTube descriptions."""
    u = (source_url or "").strip()
    if u.startswith(("http://", "https://")) and not any(h in u.lower() for h in ("localhost", "127.0.0.1", "0.0.0.0")):
        return u

    # Fallback 1: check sibling clips or live state file for a real https:// stream URL from this channel
    if channel_slug:
        state_path = STUDIO_ROOT / "renders" / "live_buffer" / f"state_{channel_slug}.json"
        if state_path.exists():
            try:
                su = str(json.loads(state_path.read_text(encoding="utf-8")).get("url") or "").strip()
                if su.startswith(("http://", "https://")) and "localhost" not in su.lower():
                    return su
            except Exception:
                pass
        ch_dir = LIVE_CLIPS_DIR / channel_slug
        if ch_dir.is_dir():
            for mj in sorted(ch_dir.glob("*/moment.json"), reverse=True)[:10]:
                try:
                    su = str(json.loads(mj.read_text(encoding="utf-8")).get("source") or "").strip()
                    if su.startswith(("http://", "https://")) and "localhost" not in su.lower():
                        return su
                except Exception:
                    continue

    # Fallback 2: known public creator channel URL
    s_key = (streamer or "").strip().lower()
    if s_key in _CREATOR_PUBLIC_URLS:
        return _CREATOR_PUBLIC_URLS[s_key]
    return ""


def _scrub_local_paths(text: str) -> str:
    """Defense-in-depth scrub ensuring no local machine paths ever leak into public YouTube descriptions."""
    cleaned_lines: list[str] = []
    for line in (text or "").splitlines():
        if _LOCAL_PATH_RE.search(line):
            # Drop lines like 'Watch full stream: /home/...' entirely rather than leaving a broken label
            if re.match(r"^\s*(?:watch\s+full\s+stream|source\s+stream|file|path)\s*:", line, flags=re.I):
                continue
            line = _LOCAL_PATH_RE.sub("", line).strip()
        cleaned_lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned_lines)).strip()


def _parse_channel_identity(channel_slug: str, transcript: str = "", source_url: str = "") -> dict[str, str]:
    """Split a channel slug like 'mythpat-gta6' or 'ishowspeed-gta6' into clean Streamer, Game, Platform."""
    slug_clean = (channel_slug or "").strip()
    parts = [p for p in re.split(r"[-_\s]+", slug_clean) if p]

    game = ""
    hay = f"{slug_clean} {transcript}".lower()
    for pat, label in _GAME_PATTERNS:
        if re.search(pat, hay, flags=re.I):
            game = label
            break

    game_tokens = {"gta", "gta6", "gtavi", "gta5", "gtav", "6", "vi", "live", "stream", "clip", "clips", "vod", "gaming", "twitch", "youtube", "valorant", "minecraft", "bgmi", "fortnite"}
    streamer_parts = [p for p in parts if p.lower() not in game_tokens]
    joined_key = "".join(p.lower() for p in streamer_parts)
    first_key = streamer_parts[0].lower() if streamer_parts else ""

    if joined_key in _STREAMER_DISPLAY_MAP:
        streamer = _STREAMER_DISPLAY_MAP[joined_key]
    elif first_key in _STREAMER_DISPLAY_MAP:
        streamer = _STREAMER_DISPLAY_MAP[first_key]
    elif streamer_parts:
        streamer = " ".join(p.capitalize() for p in streamer_parts)
    else:
        streamer = "Live Streamer"

    url_low = (source_url or "").lower()
    if "twitch.tv" in url_low:
        platform = "Twitch"
    elif "youtube.com" in url_low or "youtu.be" in url_low:
        platform = "YouTube"
    else:
        platform = "Live"

    return {"streamer": streamer, "game": game, "platform": platform}


def _clean_transcript_for_analysis(text: str) -> str:
    t = re.sub(r"\bnan\b", " ", text or "", flags=re.I)
    # Fix common ASR homophones on fast gaming streams before scene/quote extraction
    for pat, rep in (
        (r"\bcups\s+everywhere\b", "cops everywhere"),
        (r"\baur\s+to\s+the\s+car\b", "out of the car"),
        (r"\bher\s+rum\b", "her room"),
        (r"\bsurely\s+room\b", "her room"),
    ):
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_clean_spoken_quote(transcript: str) -> str:
    """Pull a short, punchy, family-friendly English/Hinglish spoken quote if one stands out."""
    clean = _clean_transcript_for_analysis(transcript)
    if not clean:
        return ""
    clauses = re.split(r"(?<=[.!?])\s+|\s*[,;]\s*", clean)
    best = ""
    best_score = 0
    for c in clauses:
        c = c.strip(" \"'.,-:")
        if not c or _PROFANITY_RE.search(c):
            continue
        words = c.split()
        if not (3 <= len(words) <= 10):
            continue
        if len(c) < 14 or len(c) > 58:
            continue
        unique_ratio = len({w.lower().strip(".,!?") for w in words}) / len(words)
        if unique_ratio < 0.72:
            continue
        if words[0].lower() in ("and", "but", "so", "because", "or", "yeah", "uh", "um", "like", "nan"):
            continue
        score = 0
        if c.endswith(("!", "?")):
            score += 4
        if any(k in c.lower() for k in ("never", "believe", "insane", "crazy", "gta", "police", "cops", "car", "ferrari", "lamborghini", "thank you", "no way", "radio", "wait", "what the", "don't care", "i'm done", "i am done", "watch me", "room", "back")):
            score += 4
        alpha_ratio = sum(ch.isalpha() or ch.isspace() or ch in "?!'" for ch in c) / max(1, len(c))
        if alpha_ratio < 0.85:
            continue
        if score >= 4 and score > best_score:
            best_score = score
            best = c
    return best if best_score >= 4 else ""


def _try_gemini_clip_metadata(
    streamer: str,
    game: str,
    platform: str,
    transcript: str,
    archetype: str,
) -> dict[str, Any] | None:
    """Optional fast Gemini Flash-Lite metadata generator when GEMINI_API_KEY / GOOGLE_API_KEY is configured."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or not transcript or len(transcript.strip()) < 20:
        return None
    try:
        import urllib.request

        prompt = (
            "You are a top YouTube Shorts editor for a viral gaming clips channel called ClipSurge.\n"
            f"Streamer: {streamer}\n"
            f"Game: {game or 'Gaming'}\n"
            f"Platform: {platform}\n"
            f"Moment vibe: {archetype}\n"
            f"Transcript (may be English or Romanized Hinglish with slight ASR typos): {transcript[:700]}\n\n"
            "Return STRICT JSON ONLY with keys:\n"
            '- "titles": array of 3 punchy, human-sounding, clickable YouTube Shorts titles (each 38-78 chars, NO #Shorts suffix, NO profanity, NO fabricated facts, natural English even if transcript is Hinglish, 1 relevant emoji max)\n'
            '- "hook_line": 1-2 engaging viewer-facing sentences summarizing the real moment (NO internal metrics, NO clip scores)\n'
            '- "extra_tags": array of 4 lowercase YouTube search keywords specific to this moment\n'
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.55,
                "maxOutputTokens": 320,
                "responseMimeType": "application/json",
            },
        }).encode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={urllib.parse.quote(api_key)}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5.5) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        titles = [
            _PROFANITY_RE.sub("***", str(t).strip()).replace("#Shorts", "").replace("#shorts", "").strip()
            for t in (parsed.get("titles") or [])
            if str(t).strip()
        ]
        hook_line = str(parsed.get("hook_line") or "").strip()
        extra_tags = [str(x).strip().lower() for x in (parsed.get("extra_tags") or []) if str(x).strip()]
        if titles and hook_line:
            return {"titles": titles[:3], "hook_line": hook_line, "extra_tags": extra_tags[:5]}
    except Exception:
        return None
    return None


def _generate_viral_clip_metadata(
    channel_slug: str,
    transcript: str,
    moment_json: dict[str, Any],
    clip_id: str = "",
    clip_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Generate human-sounding, transcript-aware viral YouTube Shorts titles (3 options),
    a clean viewer-facing description hook (zero internal debug scores), and scene-specific tags.
    """
    source_url = str(moment_json.get("source") or "").strip()
    fusion = moment_json.get("fusion") or {}
    archetype = str(fusion.get("archetype") or "").strip()
    audio_score = float((moment_json.get("audio") or {}).get("score") or 0)
    chat_score = float((moment_json.get("chat") or {}).get("score") or 0)
    tier = str(fusion.get("tier") or "").upper()

    clean_tx = _clean_transcript_for_analysis(transcript)
    low = clean_tx.lower()

    ident = _parse_channel_identity(channel_slug, clean_tx, source_url)
    streamer = ident["streamer"]
    game = ident["game"]
    platform = ident["platform"]
    in_game = f"in {game}" if game else "on Stream"
    game_lbl = game or "Live Stream"

    # 1. Try Groq (qwen/qwen3.8-27b, 0 local VRAM, <0.6s) first, then Gemini Flash-Lite if configured
    chat_meta = moment_json.get("chat") or {}
    matched_dono_for_ai = chat_meta.get("matched_dono") if chat_meta.get("dono_read_verified") else None
    ai_meta = None
    try:
        try:
            from scripts.groq_clip_brain import groq_generate_clip_metadata
        except ImportError:
            from groq_clip_brain import groq_generate_clip_metadata
        ai_meta = groq_generate_clip_metadata(
            streamer=streamer,
            game=game,
            platform=platform,
            transcript=clean_tx,
            archetype=archetype,
            matched_dono=matched_dono_for_ai,
            clip_dir=clip_dir,
        )
    except Exception:
        ai_meta = None

    if not ai_meta:
        ai_meta = _try_gemini_clip_metadata(streamer, game, platform, clean_tx, archetype)
    if ai_meta:
        titles = ai_meta["titles"]
        return {
            "title": titles[0],
            "title_options": titles,
            "hook_line": ai_meta["hook_line"],
            "extra_tags": ai_meta["extra_tags"],
            "streamer": streamer,
            "game": game,
            "platform": platform,
            "source_url": source_url,
        }

    # 2. High-precision local scene & transcript analyzer (works on English + Romanized Hinglish)
    titles: list[str] = []
    hook_line = ""
    extra_tags: list[str] = []

    has_lamborghini = bool(re.search(r"\b(?:lamborghini|lanbarginee|lambo|hurakan|huracan)\b", low))
    has_ferrari = bool(re.search(r"\b(?:ferrari|pharaari|farari)\b", low))
    has_police = bool(re.search(r"\b(?:police|pulis|cops|arrest|busted|wanted|chase)\b", low))
    has_arrest = bool(re.search(r"\b(?:arrest|busted|handcuff)\b", low))
    has_gta5_cmp = bool(re.search(r"\b(?:gt5|gta\s*5|gtav|gta\s*jaisa)\b", low))
    has_car_stolen_back = bool(re.search(r"\b(?:got\s+(?:his|her|their|my)\s+car\s+back|stole\s+my\s+car|took\s+(?:his|my)\s+car\s+back)\b", low))
    has_steal_car = bool(re.search(r"\b(?:chura|steal(?:ing)?\s*(?:a\s*)?car|gaadi\s*chura|hijack|out\s+of\s+the\s+car|get\s+out\s+(?:of\s+)?the\s+car)\b", low))
    has_crash_stunt = bool(re.search(r"\b(?:crashed|wrecked|flipped|helicopter|jet|boat|motorcycle|bike|ramp|flying)\b", low))
    has_fight = bool(re.search(r"\b(?:punched|knocked\s+out|fight(?:ing)?|slapped|beat\s+(?:him|her|me)|shoot(?:ing)?)\b", low))
    has_done_quit = bool(re.search(r"\b(?:i\s+am\s+done|i'm\s+done|im\s+done|i\s+quit|uninstall)\b", low))
    has_room_chat = bool(re.search(r"\b(?:her\s+room|see\s+her\s+room|give\s+her\s+room)\b", low))
    has_emotional = bool(re.search(r"\b(?:rona|cry(?:ing)?|tears|emotional|grateful|mehnat|dil\s*se|thank\s*you)\b", low))
    has_viewership = bool(re.search(r"\b(?:viewership|views|watching|live\s*viewers|\d{2,3},?000\s*log)\b", low))
    has_compete_speed = (streamer.lower() != "ishowspeed") and bool(
        re.search(r"\b(?:aayushu\s*speed|ishowspeed|speed)\b", low) and re.search(r"\b(?:compet\w*|vs|beating|pass)\b", low)
    )
    has_killed_rage = bool(re.search(r"\b(?:killed\s*me|he\s*killed|got\s*killed|wasted|destroyed\s*me)\b", low))
    has_jason_lucia = re.search(r"\b(jason|lucia)\b", low)
    has_location = re.search(r"\b(vice\s*city|leonida(?:\s*keys)?|harbor\s*bridge|google\s*maps)\b", low)
    has_military_mission = bool(re.search(r"\b(?:military|operation|mission|heist|under\s*bridge)\b", low))
    has_fan_shoutout = bool(re.search(r"\b(?:big\s*fan|watching\s*your\s*stream|love\s*you\s*bro)\b", low))
    has_food_chill = bool(re.search(r"\b(?:chips|rice|khaan|bhukh|hungry|garom|garam|lights\s*mein)\b", low))
    has_graphics = bool(re.search(r"\b(?:graphics|realistic|details\s+are\s+(?:crazy|insane)|looks\s+so\s+real)\b", low))

    chat_meta = moment_json.get("chat") or {}
    vis_meta = moment_json.get("visual") or {}
    matched_dono = chat_meta.get("matched_dono") or chat_meta.get("top_weird_dono") or None
    has_weird_dono = bool(chat_meta.get("dono_read_verified") and matched_dono)
    has_weird_glitch = bool(chat_meta.get("is_weird_spike")) or bool(re.search(r"\b(?:glitch(?:ed|ing)?|bugged|ragdoll|broke\s+the\s+game|cursed|wonky)\b", low))
    has_facecam_antics = bool(vis_meta.get("facecam_antics"))

    viewer_match = re.search(r"\b(\d{2,3}),?000\b", low)
    viewer_k = f"{viewer_match.group(1)}K" if viewer_match else ""

    if has_weird_dono and matched_dono:
        dono_label = "SuperChat" if platform == "YouTube" else ("Twitch Cheer" if "bits" in str(matched_dono.get("source", "")) else "Donation")
        dono_msg = str(matched_dono.get("msg") or "").strip()[:90]
        article = "an Unhinged" if dono_label == "SuperChat" else "a Wild"
        titles = [
            f"{streamer} Reads {article} {dono_label} Live {in_game}! 💀",
            f"Who Sent This Wild {dono_label} to {streamer}?! 😂",
            f"This {dono_label} Caught {streamer} Completely Off Guard! 🤯",
        ]
        hook_line = (
            f'{streamer} reads a wild {dono_label} live {in_game}: "{dono_msg}" — watch his reaction!'
            if dono_msg
            else f"{streamer} reads a wild {dono_label} live during his {game_lbl} stream and his reaction is priceless!"
        )
        extra_tags = [f"{streamer.lower()} {dono_label.lower()}", f"{streamer.lower()} donation reaction", "weird superchat", "funny stream donation"]

    elif has_weird_glitch:
        titles = [
            f"{streamer} Witnesses a Cursed {game_lbl} Glitch Live! 💀",
            f"Wait What Just Happened to This {game_lbl} NPC?! 😂",
            f"{streamer} Broke {game_lbl} Physics on Live Stream! 🤯",
        ]
        hook_line = f"Something completely wonky just happened live {in_game} and {streamer}'s chat immediately flooded with AYO/GLITCH!"
        extra_tags = [f"{game_lbl.lower()} glitch", f"{game_lbl.lower()} bugs", f"{game_lbl.lower()} funny moments", f"{streamer.lower()} reaction"]

    elif has_facecam_antics and (audio_score >= 12.0 or chat_score >= 12.0):
        titles = [
            f"{streamer} Completely Loses It on Camera {in_game}! 🤯",
            f"Watch {streamer}'s Facecam Reaction {in_game}! 💀",
            f"{streamer} Could Not Stay in His Chair Playing {game_lbl}! 😂",
        ]
        hook_line = f"Watch {streamer}'s wild facecam reaction live {in_game} — pure unfiltered stream chaos!"
        extra_tags = [f"{streamer.lower()} reaction", f"{streamer.lower()} funny", f"{streamer.lower()} chaos"]

    elif has_emotional and (viewer_k or has_viewership or "rona" in low or "cry" in low):
        if viewer_k:
            titles = [
                f"{streamer} Almost Cries Seeing {viewer_k} Live Viewers {in_game}! 🥹",
                f"{streamer} Gets Emotional Over {viewer_k} Live Viewers! ❤️",
                f"Wholesome Moment: {streamer} Thanks {viewer_k} Live Viewers {in_game}!",
            ]
            hook_line = f"{streamer} gets genuinely emotional seeing {viewer_k} fans watching his {game_lbl} live stream together — pure wholesome vibes."
            extra_tags = [f"{streamer.lower()} emotional", f"{streamer.lower()} {viewer_k.lower()} live", f"{game_lbl.lower()} emotional moment", "wholesome gaming moment"]
        else:
            titles = [
                f"{streamer}'s Emotional Moment Playing {game_lbl} Live! ❤️",
                f"{streamer} Opens Up Live During {game_lbl} Stream! 🥹",
                f"Real Talk From {streamer} Playing {game_lbl} Live!",
            ]
            hook_line = f"{streamer} shares a heartfelt, genuine moment with chat while playing {game_lbl} live."
            extra_tags = [f"{streamer.lower()} emotional", f"{streamer.lower()} heartfelt moment", "wholesome streamer moment"]

    elif has_compete_speed:
        titles = [
            f"{streamer} Responds to Competing With IShowSpeed {in_game}! 🔥",
            f"{streamer} Clears Up the IShowSpeed Viewership Comparison! 💯",
            f"Is {streamer} Competing With IShowSpeed in {game_lbl}? His Reply!",
        ]
        hook_line = f"Chat asks {streamer} if he's competing with IShowSpeed on {game_lbl} live viewership — watch his classy response!"
        extra_tags = [f"{streamer.lower()} ishowspeed", "ishowspeed vs mythpat", f"{game_lbl.lower()} live viewership", "indian gaming reaction"]

    elif has_viewership and ("doesn't matter" in low or "nahi dikh" in low or "viewership" in low):
        titles = [
            f"{streamer}'s Honest Take on {game_lbl} Live Viewership! 💯",
            f"Why {streamer} Refuses to Look at Live Viewers {in_game}! ❤️",
            f"{streamer} Gets Real About Views While Playing {game_lbl}!",
        ]
        hook_line = f"{streamer} explains why live viewership numbers don't matter to him while enjoying {game_lbl} with his community."
        extra_tags = [f"{streamer.lower()} viewership", f"{streamer.lower()} honest reaction", f"{game_lbl.lower()} live stream"]

    elif has_ferrari and has_gta5_cmp:
        titles = [
            f"{streamer} Finds a Ferrari & Says {game_lbl} Is NOTHING Like GTA 5! 🔥",
            f'{streamer} Steals a Ferrari {in_game} — "Nothing Like GTA 5!" 🏎️',
            f"{streamer}'s Insane Reaction to Finding a Ferrari {in_game}! 🤯",
        ]
        hook_line = f"{streamer} spots a Ferrari {in_game} and can't believe how next-level the game feels compared to GTA 5!"
        extra_tags = ["gta 6 ferrari", "gta 6 vs gta 5", "gta 6 cars", f"{streamer.lower()} ferrari"]

    elif has_lamborghini and has_police:
        titles = [
            f"{streamer} Refuses to Fight {game_lbl} Police in a Lamborghini! 😂",
            f"{streamer} Spots a Lamborghini {in_game} & Avoids the Cops! 🏎️",
            f"{streamer} Wants No Smoke With {game_lbl} Police! 🚨",
        ]
        hook_line = f"{streamer} eyes a Lamborghini Huracan {in_game} but refuses to start a fight with the police around the crowd!"
        extra_tags = ["gta 6 lamborghini", "gta 6 police", "gta 6 supercars", f"{streamer.lower()} gta 6 funny"]

    elif has_car_stolen_back:
        titles = [
            f"{streamer} Steals a Car & the NPC Takes It RIGHT Back {in_game}! 😂",
            f"NO WAY This {game_lbl} NPC Got His Car Back From {streamer}! 💀",
            f"{streamer} Gets Outsmarted by an NPC {in_game}! 🤯",
        ]
        hook_line = f"{streamer} tries to carjack an NPC with cops everywhere {in_game} — and can't believe it when they take their car right back!"
        extra_tags = ["gta 6 npc", "gta 6 carjacking", "gta 6 cops", f"{streamer.lower()} gta 6 funny"]

    elif has_police:
        if has_arrest:
            titles = [
                f"{streamer} Witnesses a Wild Police Arrest {in_game}! 🚨",
                f"{game_lbl} Police AI Caught {streamer} Off Guard! 🤯",
                f"{streamer} Hides From the Cops During a {game_lbl} Arrest! 😂",
            ]
            hook_line = f"{streamer} stumbles right onto an active police arrest {in_game} and tries to keep a low profile!"
            extra_tags = ["gta 6 police arrest", "gta 6 police ai", "gta 6 cops", "gta 6 details"]
        else:
            titles = [
                f"{streamer} Gets Surrounded by Cops {in_game}! 🚨",
                f"{streamer} Tries to Escape the Cops {in_game}! 🔥",
                f"Hilarious {game_lbl} Police Moment on {streamer}'s Stream! 😂",
            ]
            hook_line = f"Things get chaotic fast when {streamer} runs into cops everywhere live {in_game}!"
            extra_tags = ["gta 6 police", "gta 6 chase", "gta 6 funny moments"]

    elif has_ferrari or has_lamborghini:
        car = "Ferrari" if has_ferrari else "Lamborghini"
        titles = [
            f"{streamer} Finds an Insane {car} {in_game}! 🏎️",
            f"{streamer}'s Reaction to Seeing a {car} {in_game}! 🔥",
            f"Driving a {car} Live {in_game} — {streamer} Goes Crazy!",
        ]
        hook_line = f"{streamer} spots a {car} live {in_game} and immediately reacts to how insane the cars look!"
        extra_tags = [f"gta 6 {car.lower()}", "gta 6 supercars", "gta 6 gameplay cars"]

    elif has_steal_car:
        titles = [
            f"{streamer} Tries to Carjack an NPC Live {in_game}! 🚗",
            f"Hilarious Carjacking Fail on {streamer}'s {game_lbl} Stream! 😂",
            f"{streamer} Tests Stealing Cars Live {in_game}! 🔥",
        ]
        hook_line = f"{streamer} tries to pull someone out of their car live {in_game} and chaos immediately breaks out!"
        extra_tags = ["gta 6 car theft", "gta 6 details", "gta 6 mechanics", f"{streamer.lower()} gta 6"]

    elif has_room_chat:
        titles = [
            f'{streamer} Tells Chat "I Don\'t Care About Her Room!" ({game_lbl}) 😂',
            f"Chat Keeps Asking {streamer} to Check Her Room {in_game}! 💀",
            f"{streamer} Calls Out Chat Live During {game_lbl}! 😂",
        ]
        hook_line = f"Chat won't stop spamming {streamer} about checking her room {in_game} — watch his hilarious response!"
        extra_tags = [f"{streamer.lower()} chat", f"{streamer.lower()} funny", "gta 6 funny moments"]

    elif has_crash_stunt:
        titles = [
            f"{streamer}'s Wildest Vehicle Chaos Live {in_game}! 💥",
            f"How Did {streamer} Just Do That {in_game}?! 🤯",
            f"{streamer} Completely Wrecks Everything {in_game}! 😂",
        ]
        hook_line = f"{streamer} pulls off pure driving chaos live {in_game} — watch how this stunt ends!"
        extra_tags = ["gta 6 crash", "gta 6 driving", "gta 6 physics", f"{streamer.lower()} gta 6"]

    elif has_fight:
        titles = [
            f"{streamer} Starts a Wild Street Fight {in_game}! 💥",
            f"{streamer} vs {game_lbl} NPCs Gets Out of Hand! 😂",
            f"Instant Chaos When {streamer} Picks a Fight {in_game}! 💀",
        ]
        hook_line = f"{streamer} gets into an all-out brawl live {in_game} and things escalate immediately!"
        extra_tags = ["gta 6 fight", "gta 6 combat", "gta 6 npc", f"{streamer.lower()} gta 6"]

    elif has_done_quit:
        titles = [
            f'{streamer} Says "I Am Done!" Live {in_game}! 💀',
            f"{game_lbl} Finally Broke {streamer} Live on Stream! 😂",
            f"{streamer} Almost Quits After This {game_lbl} Moment! 🤯",
        ]
        hook_line = f"{streamer} hits his breaking point live {in_game} and says he's completely done!"
        extra_tags = [f"{streamer.lower()} rage", f"{streamer.lower()} funny", "gta 6 fail"]

    elif has_killed_rage:
        titles = [
            f"{streamer} Gets Destroyed & Completely Loses It {in_game}! 💀",
            f"{streamer} Rages After Getting Taken Out {in_game}! 😂",
            f"Instant Karma Hits {streamer} Live {in_game}! 🤯",
        ]
        hook_line = f"{streamer} gets caught completely off guard and loses his mind after getting taken out live {in_game}!"
        extra_tags = [f"{streamer.lower()} rage", f"{streamer.lower()} funny moments", "gaming rage clip", "gta 6 fail"]

    elif has_jason_lucia:
        char_name = has_jason_lucia.group(1).capitalize()
        titles = [
            f"{streamer} Reacts to This Crazy {game_lbl} {char_name} Cutscene! 🤯",
            f"This {game_lbl} {char_name} Scene Had {streamer} Speechless! 🔥",
            f"{streamer}'s Live Reaction to {char_name} {in_game}! 😂",
        ]
        hook_line = f"{streamer} reacts live to an intense {char_name} story moment {in_game} — chat couldn't believe the dialogue!"
        extra_tags = [f"gta 6 {char_name.lower()}", "gta 6 story", "gta 6 cutscene", f"{streamer.lower()} reaction"]

    elif has_location:
        loc_name = has_location.group(1).title()
        titles = [
            f"{streamer} Explores {loc_name} Live {in_game}! 🌴",
            f"{streamer} Can't Believe How Real {loc_name} Looks {in_game}! 🤯",
            f"Cruising Through {loc_name} {in_game} With {streamer}! 🔥",
        ]
        hook_line = f"{streamer} takes in the insane map details around {loc_name} live {in_game}!"
        extra_tags = [f"gta 6 {loc_name.lower()}", "gta 6 map", "gta 6 graphics"]

    elif has_military_mission:
        titles = [
            f"{streamer} Runs Into a Wild {game_lbl} Mission Moment! 🔥",
            f"Wait Until You See This {game_lbl} Scene With {streamer}! 🤯",
            f"{streamer} Reacts to a Crazy Operation {in_game}! 💀",
        ]
        hook_line = f"{streamer} dives straight into an intense story operation live {in_game} — watch how it plays out!"
        extra_tags = ["gta 6 mission", "gta 6 story mode", "gta 6 cutscene"]

    elif has_fan_shoutout:
        titles = [
            f"Wholesome Fan Shoutout on {streamer}'s {game_lbl} Stream! ❤️",
            f"{streamer} Makes a Fan's Day Live {in_game}! 🥹",
            f"{streamer}'s Best Chat Interaction During {game_lbl} Live!",
        ]
        hook_line = f"A super wholesome moment as {streamer} reacts to a fan's message live during his {game_lbl} stream."
        extra_tags = [f"{streamer.lower()} fans", "wholesome stream moment", f"{streamer.lower()} live"]

    elif has_graphics:
        titles = [
            f"{streamer} Can't Believe These {game_lbl} Graphics! 🤯",
            f"These {game_lbl} Graphics Blew {streamer}'s Mind! 🔥",
            f"{streamer} Reacts to Insane {game_lbl} Realism Live! 👀",
        ]
        hook_line = f"{streamer} stops in shock reacting to how crazy realistic {game_lbl}'s graphics look live on stream!"
        extra_tags = ["gta 6 graphics", "gta 6 realism", "gta 6 details", f"{streamer.lower()} reaction"]

    elif has_food_chill:
        titles = [
            f"{streamer}'s Hilarious Mid-Stream Rant Playing {game_lbl}! 😂",
            f"{streamer} Struggling With Studio Lights & Hunger {in_game}! 💀",
            f"Peak {streamer} Comedy During {game_lbl} Live Stream! 😂",
        ]
        hook_line = f"Classic {streamer} comedy mid-stream — complaining about studio heat and snacks while playing {game_lbl} live!"
        extra_tags = [f"{streamer.lower()} funny", f"{streamer.lower()} comedy", "indian gaming funny"]

    else:
        quote = _extract_clean_spoken_quote(clean_tx)
        seed = sum(ord(ch) for ch in (clip_id or clean_tx[:40] or streamer))
        if quote:
            titles = [
                f'{streamer}: "{quote}" ({game_lbl}) 😂',
                f"{streamer} Loses His Mind Playing {game_lbl} Live! 🤯",
                f"Chat Went Wild Over This {streamer} {game_lbl} Moment! 🔥",
            ]
            hook_line = f'{streamer} dropped an unforgettable line live {in_game}: "{quote}" — watch the full reaction!'
        elif tier == "S-TIER" or audio_score >= 70:
            bank = [
                (
                    f"{streamer} Completely Loses His Mind {in_game}! 🤯",
                    f"{streamer} goes full chaos mode playing {game_lbl} live — you have to see this reaction!",
                ),
                (
                    f"{streamer}'s Loudest Reaction Playing {game_lbl} Live! 💀",
                    f"Peak energy from {streamer} on {platform} while playing {game_lbl} live!",
                ),
                (
                    f"No Way This Just Happened to {streamer} {in_game}! 🔥",
                    f"An unbelievable live stream moment from {streamer} playing {game_lbl} that had chat going crazy!",
                ),
            ]
            pick = bank[seed % len(bank)]
            titles = [pick[0]] + [b[0] for b in bank if b[0] != pick[0]]
            hook_line = pick[1]
        elif chat_score >= 60:
            bank = [
                (
                    f"Chat Went Crazy Over This {streamer} {game_lbl} Moment! 🔥",
                    f"{streamer}'s live chat completely blew up during this hilarious {game_lbl} stream moment!",
                ),
                (
                    f"{streamer} Could NOT Believe This Happened {in_game}! 😂",
                    f"Watch {streamer}'s live reaction {in_game} that sent the entire chat into overdrive!",
                ),
                (
                    f"This {streamer} {game_lbl} Clip Broke the Chat! 💀",
                    f"One of the funniest moments from {streamer}'s {game_lbl} live stream!",
                ),
            ]
            pick = bank[seed % len(bank)]
            titles = [pick[0]] + [b[0] for b in bank if b[0] != pick[0]]
            hook_line = pick[1]
        else:
            bank = [
                (
                    f"{streamer}'s Wildest Moment Playing {game_lbl} Live! 🔥",
                    f"Catch this standout highlight clipped live from {streamer}'s {game_lbl} stream!",
                ),
                (
                    f"{streamer} Was Not Ready for This {in_game}! 😂",
                    f"{streamer} gets caught off guard during his {game_lbl} live stream — watch till the end!",
                ),
                (
                    f"Peak {streamer} Chaos Live {in_game}! 💀",
                    f"Non-stop entertainment from {streamer}'s {game_lbl} live stream on {platform}!",
                ),
            ]
            pick = bank[seed % len(bank)]
            titles = [pick[0]] + [b[0] for b in bank if b[0] != pick[0]]
            hook_line = pick[1]

    clean_titles: list[str] = []
    for t in titles:
        t = _PROFANITY_RE.sub("***", re.sub(r"\s+", " ", t).strip())
        if t and t not in clean_titles:
            clean_titles.append(t[:90])

    return {
        "title": clean_titles[0] if clean_titles else f"{streamer} Live {game_lbl} Highlight! 🔥",
        "title_options": clean_titles[:3],
        "hook_line": hook_line,
        "extra_tags": extra_tags,
        "streamer": streamer,
        "game": game,
        "platform": platform,
        "source_url": source_url,
    }


def _looks_like_clean_english_hook(text: str) -> bool:
    """Heuristic check so garbled or truncated ASR transcripts don't become raw YouTube titles."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) < 12 or t.endswith("..."):
        return False
    if _PROFANITY_RE.search(t):
        return False
    words = t.split()
    if len(words) < 3 or len(words) > 12:
        return False
    # Reject repetitive filler loops ("Bye. Bye. Bye.")
    unique_ratio = len({w.lower().strip(".,!?") for w in words}) / max(1, len(words))
    return unique_ratio >= 0.70


def resolve_target_package(target: str, target_type: str | None = None, channel: str | None = None) -> dict[str, Any]:
    """
    Resolve a studio project slug, live clip id, or direct MP4 path into a normalized package dict.
    """
    # 1. Live clip lookup
    if target_type == "clip" or (channel and (LIVE_CLIPS_DIR / channel / target).exists()):
        clip_dir = LIVE_CLIPS_DIR / (channel or "") / target
        if not clip_dir.exists():
            # Search across channels
            for ch_dir in LIVE_CLIPS_DIR.iterdir() if LIVE_CLIPS_DIR.exists() else []:
                if (ch_dir / target).is_dir():
                    clip_dir = ch_dir / target
                    channel = ch_dir.name
                    break
        if not clip_dir.exists():
            raise FileNotFoundError(f"Live clip '{target}' not found.")
        mp4s = sorted(clip_dir.glob("*.mp4"))
        if not mp4s:
            raise FileNotFoundError(f"No MP4 found in {clip_dir}")
        return {
            "kind": "clip",
            "id": clip_dir.name,
            "channel": channel or clip_dir.parent.name,
            "folder": clip_dir,
            "video_path": mp4s[0],
        }

    # 2. Studio export slug
    proj_dir = EXPORTS_DIR / target
    if target_type == "project" or (proj_dir.is_dir() and list(proj_dir.glob("*.mp4"))):
        mp4s = sorted(proj_dir.glob("*.mp4"))
        if not mp4s:
            raise FileNotFoundError(f"No MP4 found in {proj_dir}")
        return {
            "kind": "project",
            "id": target,
            "channel": None,
            "folder": proj_dir,
            "video_path": mp4s[0],
        }

    # 3. Direct file or folder path
    p = Path(target).expanduser()
    if not p.is_absolute():
        p = (STUDIO_ROOT / p).resolve()
    if p.is_dir():
        mp4s = sorted(p.glob("*.mp4"))
        if not mp4s:
            raise FileNotFoundError(f"No MP4 found in {p}")
        p = mp4s[0]
    if not p.exists():
        raise FileNotFoundError(f"Video not found: {target}")
    kind = "clip" if LIVE_CLIPS_DIR in p.parents else ("project" if EXPORTS_DIR in p.parents else "file")
    return {
        "kind": kind,
        "id": p.parent.name if kind != "file" else p.stem,
        "channel": p.parent.parent.name if kind == "clip" else None,
        "folder": p.parent,
        "video_path": p,
    }


def is_human_approved(folder: Path) -> bool:
    """Check CreatorRadar Rule 4 human approval status from checklist.md or project.json."""
    proj_json = folder / "project.json"
    if proj_json.exists():
        try:
            if json.loads(proj_json.read_text(encoding="utf-8")).get("human_approved"):
                return True
        except Exception:
            pass
    check_path = folder / "checklist.md"
    if check_path.exists():
        txt = check_path.read_text(encoding="utf-8")
        if ("- [ ]" not in txt) and ("- [x]" in txt.lower()):
            return True
    return False


def mark_human_approved(folder: Path):
    check_path = folder / "checklist.md"
    if check_path.exists():
        txt = check_path.read_text(encoding="utf-8")
        txt = re.sub(r"- \[ \]", "- [x]", txt)
        check_path.write_text(txt, encoding="utf-8")
    proj_json = folder / "project.json"
    if proj_json.exists():
        try:
            m = json.loads(proj_json.read_text(encoding="utf-8"))
            m["human_approved"] = True
            proj_json.write_text(json.dumps(m, indent=2), encoding="utf-8")
        except Exception:
            pass


def read_upload_receipt(folder: Path) -> dict[str, Any] | None:
    receipt_path = folder / "youtube_upload.json"
    if not receipt_path.exists():
        return None
    try:
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_upload_history() -> list[dict[str, Any]]:
    """Read persistent upload receipts stored in config/youtube_upload_history.json (survives local clip cleanup)."""
    if not UPLOAD_HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(UPLOAD_HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def append_upload_history(receipt: dict[str, Any]):
    """Append or update an upload receipt in config/youtube_upload_history.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    hist = load_upload_history()
    vid = receipt.get("video_id")
    hist = [r for r in hist if not (vid and r.get("video_id") == vid)]
    hist.insert(0, receipt)
    tmp = UPLOAD_HISTORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(hist[:500], indent=2), encoding="utf-8")
    tmp.replace(UPLOAD_HISTORY_PATH)


def mark_upload_staged(receipt: dict[str, Any], status: str = "staged") -> dict[str, Any]:
    """
    Tag an upload receipt as awaiting the publish agent.

    Staged clips stay private on YouTube and keep their local package so
    scripts/publish_agent.py can run the human reviewer before deciding
    publish vs. delete. See scripts/publish_agent.py for the state machine.
    """
    if not receipt.get("video_id"):
        return receipt
    staged = dict(receipt)
    staged["publish_status"] = status
    staged.setdefault(
        "staged_at",
        receipt.get("uploaded_at") or datetime.now(timezone.utc).isoformat(),
    )
    append_upload_history(staged)
    return staged


def _manage_youtube_client(profile: str | None = "clipper"):
    """Authenticated YouTube client for videos.update / videos.delete (needs force-ssl)."""
    _, _, _, build, HttpError, _ = _lazy_google_imports()
    creds, channel = load_credentials(refresh_if_needed=True, profile=profile)
    if creds is None:
        prof = normalize_profile(profile)
        raise YouTubeScopeError(
            f"No saved YouTube credentials for profile '{prof}'. Run:\n"
            f"    .venv/bin/python scripts/youtube_uploader.py --auth --profile {prof}"
        )
    return build("youtube", "v3", credentials=creds, cache_discovery=False), HttpError, channel


def _raise_if_scope_error(exc: Exception, profile: str | None) -> None:
    """Convert a missing-force-ssl 403 into an actionable re-auth message."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    body = str(getattr(exc, "content", "") or "")
    if status == 403 and ("scope" in body.lower() or "insufficient" in body.lower() or "permission" in body.lower()):
        raise YouTubeScopeError(_manage_scope_hint(profile)) from exc


def set_video_privacy(
    video_id: str,
    privacy: str,
    publish_at: str | None = None,
    profile: str | None = "clipper",
) -> dict[str, Any]:
    """
    Change a video's privacyStatus (and optionally schedule publishAt).

    privacy: 'private' | 'unlisted' | 'public'
    publish_at: RFC3339 UTC timestamp; only valid together with privacy='private'.
                Pass '' to clear a previously scheduled publish time.
    """
    privacy = str(privacy or "").strip().lower()
    if privacy not in ("private", "unlisted", "public"):
        raise ValueError(f"invalid privacyStatus: {privacy!r}")
    if publish_at and privacy != "private":
        raise ValueError("publishAt is only valid with privacyStatus='private'")

    yt, HttpError, _ = _manage_youtube_client(profile)
    status: dict[str, Any] = {"privacyStatus": privacy}
    if publish_at:
        status["publishAt"] = publish_at

    try:
        yt.videos().update(part="status", body={"id": video_id, "status": status}).execute()
    except HttpError as exc:
        _raise_if_scope_error(exc, profile)
        raise

    return {"video_id": video_id, "privacyStatus": privacy, "publishAt": publish_at or None}


def delete_video(video_id: str, profile: str | None = "clipper") -> dict[str, Any]:
    """Permanently delete a video from the channel. Irreversible."""
    yt, HttpError, _ = _manage_youtube_client(profile)
    try:
        yt.videos().delete(id=video_id).execute()
    except HttpError as exc:
        _raise_if_scope_error(exc, profile)
        raise
    return {"video_id": video_id, "deleted": True}


def build_upload_metadata(
    target: str,
    target_type: str | None = None,
    channel: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a complete, YouTube-ready metadata payload (title, description, hashtags,
    tags, category_id, privacy_status, is_short, human_approved) for any project,
    live clip, or standalone MP4.
    """
    pkg = resolve_target_package(target, target_type=target_type, channel=channel)
    folder: Path = pkg["folder"]
    video_path: Path = pkg["video_path"]
    vinfo = probe_video_info(video_path)
    is_short = vinfo["is_short"]
    is_clip = pkg["kind"] == "clip"

    meta_md = (folder / "metadata.md").read_text(encoding="utf-8") if (folder / "metadata.md").exists() else ""
    project_json = {}
    if (folder / "project.json").exists():
        try:
            project_json = json.loads((folder / "project.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    moment_json = {}
    if (folder / "moment.json").exists():
        try:
            moment_json = json.loads((folder / "moment.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    transcript_json = {}
    if (folder / "transcript.json").exists():
        try:
            transcript_json = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    def _format_shorts_title(t: str) -> str:
        t = re.sub(r"\s+", " ", t).strip()
        if is_short and "#shorts" not in t.lower():
            if len(t) + 8 <= 98:
                t = f"{t} #Shorts"
            else:
                t = t[:88].rstrip(" .,-:") + " #Shorts"
        return t[:100].strip()

    # --- 1. Determine Title & Viral Clip Metadata ---
    raw_title = ""
    title_options: list[str] = []
    clip_meta: dict[str, Any] | None = None
    if is_clip:
        full_transcript = re.sub(
            r"\s+",
            " ",
            str(transcript_json.get("text") or moment_json.get("transcript") or ""),
        ).strip()
        clip_meta = _generate_viral_clip_metadata(
            channel_slug=pkg.get("channel") or "",
            transcript=full_transcript,
            moment_json=moment_json,
            clip_id=pkg.get("id") or "",
            clip_dir=folder,
        )
        raw_title = clip_meta["title"]
        title_options = [_format_shorts_title(opt) for opt in clip_meta.get("title_options", [])]
        context_for_tags = f"{clip_meta['streamer']} {clip_meta['game']} {raw_title} {full_transcript}"
    else:
        m_opt1 = re.search(r"## Title Options\s+1\.\s+`?([^`\n]+)`?", meta_md)
        raw_title = (
            (m_opt1.group(1).strip() if m_opt1 else "")
            or project_json.get("topic")
            or video_path.stem.replace("-", " ").title()
        )
        title_options = [_format_shorts_title(m.group(1).strip()) for m in re.finditer(r"^\d+\.\s+`?([^`\n]+)`?", meta_md, flags=re.M)][:3]
        context_for_tags = f"{raw_title} {project_json.get('hook', '')} {meta_md}"

    hashtags, tags = _generate_smart_hashtags_and_tags(
        title=raw_title,
        context_text=context_for_tags,
        is_short=is_short,
        is_live_clip=is_clip,
        channel_slug=pkg.get("channel") or "",
        extra_tags=(clip_meta or {}).get("extra_tags"),
        streamer_name=(clip_meta or {}).get("streamer", ""),
        game_name=(clip_meta or {}).get("game", ""),
        platform_name=(clip_meta or {}).get("platform", ""),
    )

    # Ensure title fits <= 100 chars and includes #Shorts for vertical Shorts
    title = _format_shorts_title(raw_title)
    if title and title not in title_options:
        title_options = [title] + title_options[:2]

    # --- 2. Build Description with Chapters, Sources, Hashtags, and Rule 5 AI Disclosure ---
    desc_body = ""
    if is_clip and clip_meta:
        streamer = clip_meta["streamer"]
        game = clip_meta["game"]
        source_url = _sanitize_public_source_url(
            clip_meta.get("source_url", ""),
            streamer=streamer,
            channel_slug=pkg.get("channel") or "",
        )
        # Re-derive platform from the sanitized public URL so we never print '(Live)'
        if "twitch.tv" in source_url.lower():
            platform = "Twitch"
        elif "youtube.com" in source_url.lower() or "youtu.be" in source_url.lower():
            platform = "YouTube"
        else:
            platform = ""
        hook_line = clip_meta["hook_line"]
        game_phrase = f" {game}" if game else ""

        lines = [
            hook_line,
            "",
            "Subscribe to ClipSurge for daily viral gaming clips & live stream highlights!",
            f"Drop a comment with your favorite {streamer}{game_phrase} moment so far.",
        ]
        credit_line = f"Credit: {streamer} Live Stream ({platform})" if platform else f"Credit: {streamer} Live Stream"
        if source_url:
            lines.extend([
                "",
                credit_line,
                f"Watch full stream: {source_url}",
            ])
        else:
            lines.extend(["", credit_line])
        desc_body = "\n".join(lines)
    else:
        m_desc = re.search(r"## Description(?:\s*\(Draft\))?\s*\n(.*)", meta_md, flags=re.S)
        if m_desc:
            desc_body = m_desc.group(1).strip()
            # Remove duplicate inline hashtag lines so we put one clean curated hashtag block
            desc_body = re.sub(r"(?m)^(?:#\w+\s*)+$", "", desc_body).strip()
            # Clean markdown headings like ### Chapters -> Chapters:
            desc_body = re.sub(r"(?m)^###\s+(.+)$", r"\1:", desc_body)
        else:
            hook = project_json.get("hook") or f"Full breakdown of {title}."
            desc_body = hook

    desc_body = _scrub_local_paths(desc_body)
    disclosure = AI_DISCLOSURE_STUDIO
    # Rule 5 applies to Studio videos containing AI-generated graphics, animation, voiceover, or narration — NOT real live stream clips
    if (not is_clip) and ("Graphics" not in desc_body or "AI assistance" not in desc_body):
        desc_body = f"{desc_body}\n\n---\n{disclosure}".strip()

    hashtag_line = " ".join(hashtags)
    description = _scrub_local_paths(f"{desc_body}\n\n{hashtag_line}".strip())[:4950]

    # --- 3. Category ID ---
    hay = f"{title} {context_for_tags}".lower()
    if is_clip or any(k in hay for k in ("gta", "game", "gaming", "ps5", "xbox", "stream", "mythpat", "ishowspeed", "valorant", "minecraft", "esports")):
        category_id = "20"  # Gaming
    elif any(k in hay for k in ("ai ", "coding", "python", "tech", "software", "llm")):
        category_id = "28"  # Science & Technology
    else:
        category_id = "24"  # Entertainment

    # --- 4. Apply explicit user overrides ---
    overrides = overrides or {}
    if overrides.get("title"):
        title = str(overrides["title"]).strip()[:100]
    if overrides.get("hashtags") is not None:
        raw_ht = overrides["hashtags"]
        if isinstance(raw_ht, str):
            raw_ht = [h for h in re.split(r"[\s,]+", raw_ht) if h]
        hashtags = [_clean_hashtag(h) for h in raw_ht if _clean_hashtag(h)][:10]
    if overrides.get("tags") is not None:
        raw_tg = overrides["tags"]
        if isinstance(raw_tg, str):
            raw_tg = [t.strip() for t in raw_tg.split(",") if t.strip()]
        tags = [str(t).strip() for t in raw_tg if str(t).strip()]
    if overrides.get("description"):
        description = _scrub_local_paths(str(overrides["description"]).strip())
        # Ensure hashtags remain present; Rule 5 AI disclosure applies only to AI-generated Studio videos (not real live stream clips)
        if hashtags and not any(h.lower() in description.lower() for h in hashtags[:2]):
            description = f"{description}\n\n{' '.join(hashtags)}"
        if (not is_clip) and "AI assistance" not in description:
            description = f"{description}\n\n{disclosure}"
        description = description[:4950]
    if overrides.get("category_id"):
        category_id = str(overrides["category_id"])

    privacy_status = str(overrides.get("privacy_status") or "unlisted").lower()
    if privacy_status not in ("private", "unlisted", "public"):
        privacy_status = "unlisted"

    publish_at = (overrides.get("publish_at") or "").strip() or None
    if publish_at:
        # YouTube Data API requires privacyStatus='private' when publishAt is set
        privacy_status = "private"

    # Optional thumbnail search
    thumb_path = overrides.get("thumbnail_path")
    if not thumb_path:
        for cand in ("thumbnail.jpg", "thumbnail.png", "thumb.jpg", "thumb.png"):
            if (folder / cand).exists():
                thumb_path = str(folder / cand)
                break

    return {
        "kind": pkg["kind"],
        "default_profile": normalize_profile(None, kind=pkg["kind"]),
        "id": pkg["id"],
        "channel": pkg["channel"],
        "folder": str(folder),
        "video_path": str(video_path),
        "video_size_mb": round(video_path.stat().st_size / (1024 * 1024), 2),
        "video_info": vinfo,
        "is_short": is_short,
        "title": title,
        "title_options": title_options,
        "description": description,
        "hashtags": hashtags,
        "tags": tags,
        "category_id": category_id,
        "category_name": YOUTUBE_CATEGORIES.get(category_id, "Gaming"),
        "privacy_status": privacy_status,
        "publish_at": publish_at,
        "made_for_kids": bool(overrides.get("made_for_kids", False)),
        "contains_synthetic_media": bool(overrides.get("contains_synthetic_media", not is_clip)),
        "thumbnail_path": thumb_path,
        "human_approved": is_human_approved(folder),
        "existing_upload": read_upload_receipt(folder),
    }


def upload_video(
    target: str,
    target_type: str | None = None,
    channel: str | None = None,
    overrides: dict[str, Any] | None = None,
    require_approval: bool = True,
    approve_now: bool = False,
    progress_cb: Callable[[int, int, int], None] | None = None,
    profile: str | None = None,
    delete_clip_after_upload: bool = True,
) -> dict[str, Any]:
    """
    Upload a rendered video or live clip to YouTube via resumable chunked upload.
    Routes live clips to the dedicated 'clipper' YouTube channel by default so main
    studio exports ('studio') and live stream clips stay completely separated.
    Enforces CreatorRadar Rule 4 (human approval) and Rule 5 (AI disclosure).
    """
    _, _, _, build, HttpError, MediaFileUpload = _lazy_google_imports()

    meta = build_upload_metadata(target, target_type=target_type, channel=channel, overrides=overrides)
    folder = Path(meta["folder"])
    video_path = Path(meta["video_path"])

    # Content-safety gate: explicit frames are blurred before upload, and an
    # unscannable clip is blocked rather than published unchecked.
    try:
        from nsfw_guard import ensure_upload_safe
    except ImportError:
        from scripts.nsfw_guard import ensure_upload_safe
    _safety = ensure_upload_safe(folder, video_path)
    if not _safety.get("upload_ok"):
        raise PermissionError(f"Content-safety gate blocked upload: {_safety.get('reason')}")
    if _safety.get("censored_path"):
        video_path = Path(_safety["censored_path"])
        meta["video_path"] = str(video_path)
        meta["content_censored"] = True

    # Strict channel isolation: live clips ONLY upload to 'clipper' (ClipSurge),
    # studio/other videos ONLY upload to 'studio' (Paper Trail).
    if meta["kind"] == "clip":
        if profile and normalize_profile(profile) != "clipper":
            raise PermissionError(
                "Channel isolation policy: Live clips may ONLY be uploaded to the dedicated 'clipper' channel (ClipSurge), never to Paper Trail."
            )
        resolved_profile = "clipper"
    elif meta["kind"] == "project":
        if profile and normalize_profile(profile) != "studio":
            raise PermissionError(
                "Channel isolation policy: Studio videos may ONLY be uploaded to the 'studio' channel (Paper Trail), never to ClipSurge."
            )
        resolved_profile = "studio"
    else:
        resolved_profile = normalize_profile(profile, kind=meta["kind"])

    if approve_now:
        mark_human_approved(folder)
        meta["human_approved"] = True

    if require_approval and not meta["human_approved"]:
        raise PermissionError(
            "CreatorRadar Rule 4: Human approval required before uploading to YouTube. "
            "Sign off the checklist in the Studio UI or pass --approve."
        )

    creds, channel_info = load_credentials(refresh_if_needed=True, profile=resolved_profile)
    if not creds or not creds.valid:
        label = PROFILE_LABELS[resolved_profile]
        raise RuntimeError(
            f"{label} ('{resolved_profile}') is not connected yet. Connect it via the Studio UI "
            f"(YouTube Upload tab) or run: .venv/bin/python scripts/youtube_uploader.py --auth --profile {resolved_profile}"
        )

    youtube = build("youtube", "v3", credentials=creds)

    # Enforce strict 500-char YouTube tags limit
    safe_tags: list[str] = []
    tag_chars = 0
    for t in meta["tags"]:
        cost = len(t) + (3 if " " in t else 1)
        if tag_chars + cost > 480:
            break
        safe_tags.append(t)
        tag_chars += cost

    status_body: dict[str, Any] = {
        "privacyStatus": meta["privacy_status"],
        "selfDeclaredMadeForKids": meta["made_for_kids"],
    }
    if meta.get("contains_synthetic_media"):
        status_body["containsSyntheticMedia"] = True
    if meta.get("publish_at"):
        status_body["publishAt"] = meta["publish_at"]

    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"][:4950],
            "tags": safe_tags,
            "categoryId": str(meta["category_id"]),
            "defaultLanguage": "en",
        },
        "status": status_body,
    }

    total_bytes = video_path.stat().st_size
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=4 * 1024 * 1024,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retries = 0
    max_retries = 5
    while response is None:
        try:
            status, response = request.next_chunk()
            if status and progress_cb:
                pct = int(status.progress() * 100)
                progress_cb(pct, int(status.resumable_progress), total_bytes)
        except HttpError as err:
            if err.resp.status in (500, 502, 503, 504) and retries < max_retries:
                retries += 1
                time.sleep(min(2 ** retries, 16))
                continue
            raise
        except Exception:
            if retries < max_retries:
                retries += 1
                time.sleep(min(2 ** retries, 16))
                continue
            raise

    if progress_cb:
        progress_cb(100, total_bytes, total_bytes)

    video_id = response["id"]
    thumbnail_uploaded = False
    thumbnail_error = None
    if meta.get("thumbnail_path") and Path(meta["thumbnail_path"]).exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(meta["thumbnail_path"]),
            ).execute()
            thumbnail_uploaded = True
        except Exception as exc:
            thumbnail_error = str(exc)

    receipt = {
        "video_id": video_id,
        "url": f"https://youtube.com/shorts/{video_id}" if meta["is_short"] else f"https://youtu.be/{video_id}",
        "watch_url": f"https://www.youtube.com/watch?v={video_id}",
        "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
        "title": meta["title"],
        "description": meta["description"],
        "hashtags": meta["hashtags"],
        "tags": safe_tags,
        "category_id": meta["category_id"],
        "privacy_status": meta["privacy_status"],
        "publish_at": meta.get("publish_at"),
        "is_short": meta["is_short"],
        "thumbnail_uploaded": thumbnail_uploaded,
        "thumbnail_error": thumbnail_error,
        "profile": resolved_profile,
        "channel_title": (channel_info or {}).get("title"),
        "channel_id": (channel_info or {}).get("id"),
        "kind": meta["kind"],
        "clip_channel": meta.get("channel"),
        "source_id": meta.get("id"),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "local_clip_deleted": False,
        "freed_mb": 0.0,
    }
    try:
        (folder / "youtube_upload.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    except Exception:
        pass

    # Record taste memory reinforcement before deleting local clip folder
    if meta["kind"] == "clip":
        try:
            from scripts.clipper_taste_memory import record_clip_feedback
            record_clip_feedback(folder, "uploaded", channel=meta.get("channel") or "")
        except Exception:
            try:
                from clipper_taste_memory import record_clip_feedback
                record_clip_feedback(folder, "uploaded", channel=meta.get("channel") or "")
            except Exception:
                pass

    # Auto-delete local live clip folder after confirmed YouTube upload to save disk space
    if delete_clip_after_upload and meta["kind"] == "clip":
        import shutil
        resolved_folder = folder.resolve()
        clips_root = LIVE_CLIPS_DIR.resolve()
        if str(resolved_folder).startswith(str(clips_root) + os.sep) and resolved_folder.is_dir():
            freed_bytes = sum(f.stat().st_size for f in resolved_folder.rglob("*") if f.is_file())
            shutil.rmtree(resolved_folder, ignore_errors=True)
            receipt["local_clip_deleted"] = not resolved_folder.exists()
            receipt["freed_mb"] = round(freed_bytes / (1024 * 1024), 2)

    append_upload_history(receipt)
    return receipt


def run_cli_oauth_flow(port: int = 8089, open_browser: bool = False, profile: str = "studio") -> dict[str, Any]:
    """
    Start a temporary local HTTP callback listener and print the exact Google OAuth link.
    Works even without restarting dashboard/app.py!
    """
    prof = normalize_profile(profile)
    secret_info = load_client_secret_info(profile=prof)
    if not secret_info["exists"]:
        print(
            f"\n[!] Missing Google Cloud OAuth credentials!\n"
            f"    Save your downloaded client_secret.json from Google Cloud Console to:\n"
            f"    {CLIENT_SECRET_PATH}\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # Pick port matching web redirect URI if it's a web client
    redirect_uri = f"http://localhost:{port}/"
    if secret_info["client_type"] == "web":
        redirect_uri = pick_redirect_uri(f"http://localhost:{port}/", profile=prof)
        parsed_r = urllib.parse.urlparse(redirect_uri)
        if parsed_r.port:
            port = parsed_r.port

    auth_data = build_oauth_url(redirect_uri=redirect_uri, profile=prof)
    token_path = get_token_path(prof)
    result_box: dict[str, Any] = {}
    done_event = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if "error" in qs:
                result_box["error"] = qs["error"][0]
                self._respond(400, f"<h2>Authorization Cancelled</h2><p>{qs['error'][0]}</p>")
                done_event.set()
                return
            code = (qs.get("code") or [""])[0]
            state = (qs.get("state") or [""])[0]
            if not code:
                self._respond(200, "<h3>Waiting for Google OAuth callback...</h3>")
                return
            try:
                res = complete_oauth_callback(code=code, state=state, redirect_uri=redirect_uri, profile=prof)
                result_box["result"] = res
                ch = res.get("channel") or {}
                self._respond(
                    200,
                    f"<h2>{PROFILE_LABELS[prof]} Connected!</h2>"
                    f"<p>Channel: <strong>{ch.get('title')}</strong> ({ch.get('custom_url') or ch.get('id')})</p>"
                    f"<p>Refresh token saved to <code>{token_path.relative_to(STUDIO_ROOT)}</code>. You can close this tab.</p>",
                )
            except Exception as exc:
                result_box["error"] = str(exc)
                self._respond(500, f"<h2>OAuth Error</h2><pre>{exc}</pre>")
            done_event.set()

        def _respond(self, code: int, body_html: str):
            html = (
                "<!doctype html><html><head><meta charset='utf-8'><title>CreatorRadar YouTube Auth</title>"
                "<style>body{background:#080d16;color:#e2e8f0;font-family:system-ui,sans-serif;padding:48px;text-align:center}"
                "h2{color:#f47750}code,pre{background:#0f1726;padding:6px 10px;border-radius:8px;color:#38bdf8}</style>"
                f"</head><body>{body_html}</body></html>"
            ).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

    # Ensure port is bindable
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"Port {port} is busy ({exc}). Pass --port <free_port> or use the Studio Dashboard.") from exc

    server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print("\n======================================================================")
    print(f"  CreatorRadar YouTube Login — {PROFILE_LABELS[prof]} ({prof})")
    print("======================================================================")
    print(f"Callback listening on: {redirect_uri}")
    print("\nOpen this link in your browser and select the YouTube channel for this slot:\n")
    print(auth_data["auth_url"])
    print("\nWaiting for Google authorization callback (Ctrl+C to cancel)...", flush=True)

    if open_browser:
        import webbrowser
        webbrowser.open(auth_data["auth_url"])

    try:
        while not done_event.is_set():
            done_event.wait(timeout=0.5)
    finally:
        server.shutdown()
        server.server_close()

    if "error" in result_box:
        raise RuntimeError(f"OAuth failed: {result_box['error']}")
    res = result_box["result"]
    ch = res.get("channel") or {}
    print(f"\n[OK] Connected {PROFILE_LABELS[prof]}: {ch.get('title')} ({ch.get('subscribers', 0):,} subs)")
    print(f"[OK] Refresh token saved to: {token_path}")
    return res


def main():
    parser = argparse.ArgumentParser(description="CreatorRadar YouTube Data API v3 Uploader")
    parser.add_argument("--status", action="store_true", help="Print YouTube OAuth & channel connection status")
    parser.add_argument("--auth", action="store_true", help="Start Google OAuth login flow and save refresh token")
    parser.add_argument("--profile", choices=list(VALID_PROFILES), default=None, help="Channel slot: 'studio' (main) or 'clipper' (dedicated clipping channel)")
    parser.add_argument("--port", type=int, default=8089, help="Local callback port for --auth (default: 8089)")
    parser.add_argument("--open-browser", action="store_true", help="Automatically open browser during --auth")
    parser.add_argument("--disconnect", action="store_true", help="Remove saved YouTube OAuth token for --profile")
    parser.add_argument("--preview", help="Preview SEO title, hashtags, tags & description for a slug, clip_id, or MP4")
    parser.add_argument("--upload", help="Upload a project slug, clip_id, or MP4 path to YouTube")
    parser.add_argument("--type", choices=["project", "clip"], default=None, help="Explicit target type")
    parser.add_argument("--channel", default=None, help="Channel folder name when targeting a live clip")
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"], default="unlisted", help="Privacy status (default: unlisted for Content ID & HD processing clearance)")
    parser.add_argument("--publish-at", default=None, help="Schedule publish time (ISO-8601 UTC, e.g. 2026-11-19T14:00:00Z)")
    parser.add_argument("--title", default=None, help="Override video title")
    parser.add_argument("--description", default=None, help="Override description")
    parser.add_argument("--hashtags", default=None, help="Space or comma separated hashtags")
    parser.add_argument("--tags", default=None, help="Comma separated YouTube tags")
    parser.add_argument("--category", default=None, help="YouTube category ID (20=Gaming, 24=Entertainment, 28=Tech)")
    parser.add_argument("--thumbnail", default=None, help="Optional custom thumbnail JPG/PNG path")
    parser.add_argument("--approve", action="store_true", help="Explicitly confirm Rule 4 human approval and upload")
    args = parser.parse_args()

    if args.disconnect:
        print(json.dumps(disconnect_youtube(profile=args.profile or "studio"), indent=2))
        return

    if args.auth:
        run_cli_oauth_flow(port=args.port, open_browser=args.open_browser, profile=args.profile or "studio")
        return

    if args.status:
        print(json.dumps(get_youtube_status(refresh_channel=True, profile=args.profile or "studio"), indent=2))
        return

    overrides = {
        "title": args.title,
        "description": args.description,
        "hashtags": args.hashtags,
        "tags": args.tags,
        "category_id": args.category,
        "privacy_status": args.privacy,
        "publish_at": args.publish_at,
        "thumbnail_path": args.thumbnail,
    }
    overrides = {k: v for k, v in overrides.items() if v is not None}

    if args.preview:
        meta = build_upload_metadata(args.preview, target_type=args.type, channel=args.channel, overrides=overrides)
        print(json.dumps(meta, indent=2))
        return

    if args.upload:
        def _prog(pct: int, sent: int, total: int):
            mb_sent = sent / (1024 * 1024)
            mb_tot = total / (1024 * 1024)
            print(f"\r  Uploading to YouTube: {pct:3d}% ({mb_sent:.1f}/{mb_tot:.1f} MB)", end="", flush=True)
            if pct >= 100:
                print("", flush=True)

        receipt = upload_video(
            args.upload,
            target_type=args.type,
            channel=args.channel,
            overrides=overrides,
            require_approval=True,
            approve_now=args.approve,
            progress_cb=_prog,
            profile=args.profile,
        )
        print("\n[OK] Upload complete!")
        print(json.dumps(receipt, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
