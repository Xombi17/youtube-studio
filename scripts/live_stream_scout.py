#!/usr/bin/env python3
"""
CreatorRadar / ClipSurge — Live Stream Scout & Discovery Engine

Discovers currently active high-viewer live streams across Twitch (public GQL directory
+ priority creator watchlist) and YouTube (public handle live-status check, read-only,
zero bot-bypass) so the Live Clipper can launch parallel clipping sessions automatically.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

STUDIO_ROOT = Path(__file__).resolve().parent.parent
WATCHLIST_PATH = STUDIO_ROOT / "config" / "live-stream-watchlist.json"
TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
TWITCH_PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"


def load_watchlist_config() -> dict[str, Any]:
    if WATCHLIST_PATH.exists():
        try:
            return json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "default_game": "Grand Theft Auto VI",
        "default_languages": ["EN"],
        "max_parallel_default": 2,
        "max_parallel_hard_cap": 4,
        "poll_interval_sec": 120,
        "twitch_watchlist": ["ishowspeed", "kaicenat", "xqc", "caseoh_", "jynxzi"],
        "youtube_watchlist": [],
        "preset_games": ["Grand Theft Auto VI", "ALL", "Just Chatting", "VALORANT"],
    }


def _twitch_gql(query: str, variables: dict[str, Any] | None = None, timeout: float = 8.0) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    req = urllib.request.Request(
        TWITCH_GQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Client-Id": TWITCH_PUBLIC_CLIENT_ID,
            "Content-Type": "application/json",
            "User-Agent": "CreatorRadar-LiveScout/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_twitch_directory(
    game: str = "Grand Theft Auto VI",
    languages: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    langs = {l.upper() for l in (languages or []) if l and l.upper() != "ALL"}
    fetch_count = min(60, max(35, limit * 3)) if langs else max(20, limit)

    edges: list[dict[str, Any]] = []
    if game and game.upper() != "ALL":
        q = """
        query($name: String!, $first: Int!) {
          game(name: $name) {
            displayName
            streams(first: $first, options: {sort: VIEWER_COUNT}) {
              edges {
                node {
                  title
                  viewersCount
                  previewImageURL(width: 440, height: 248)
                  broadcaster { login displayName broadcastSettings { language } }
                  game { displayName }
                }
              }
            }
          }
        }
        """
        data = _twitch_gql(q, {"name": game, "first": fetch_count})
        g = (data.get("data") or {}).get("game")
        if g:
            edges = (g.get("streams") or {}).get("edges") or []
    else:
        q = """
        query($first: Int!) {
          streams(first: $first, options: {sort: VIEWER_COUNT}) {
            edges {
              node {
                title
                viewersCount
                previewImageURL(width: 440, height: 248)
                broadcaster { login displayName broadcastSettings { language } }
                game { displayName }
              }
            }
          }
        }
        """
        data = _twitch_gql(q, {"first": fetch_count})
        edges = ((data.get("data") or {}).get("streams") or {}).get("edges") or []

    out: list[dict[str, Any]] = []
    for e in edges:
        node = (e or {}).get("node") or {}
        bc = node.get("broadcaster") or {}
        login = (bc.get("login") or "").strip().lower()
        if not login:
            continue
        lang = (((bc.get("broadcastSettings") or {}).get("language")) or "EN").upper()
        if langs and lang not in langs:
            continue
        game_name = ((node.get("game") or {}).get("displayName") or game or "Live").strip()
        out.append({
            "id": f"twitch:{login}",
            "platform": "twitch",
            "login": login,
            "display_name": bc.get("displayName") or login,
            "url": f"https://www.twitch.tv/{login}",
            "title": (node.get("title") or "").strip(),
            "game": game_name,
            "viewers": int(node.get("viewersCount") or 0),
            "language": lang,
            "thumbnail_url": node.get("previewImageURL") or "",
            "clip_ready": True,
            "recommended_asr": "hinglish" if lang in ("HI", "IN") else "whistle",
            "recommended_lang": "hi" if lang in ("HI", "IN") else "en",
        })
    return out


def _fetch_twitch_watchlist(logins: list[str]) -> list[dict[str, Any]]:
    """Batch-check live status for all Twitch watchlist creators in compact GQL chunks."""
    clean = [re.sub(r"[^a-z0-9_]", "", l.lower()) for l in logins if l]
    clean = list(dict.fromkeys(c for c in clean if c))
    if not clean:
        return []
    live: list[dict[str, Any]] = []
    for chunk_start in range(0, len(clean), 8):
        batch = clean[chunk_start:chunk_start + 8]
        aliases = [
            f'u{idx}: user(login: "{login}") {{ '
            f'login displayName broadcastSettings {{ language }} '
            f'stream {{ title viewersCount previewImageURL(width: 440, height: 248) game {{ displayName }} }} '
            f'}}'
            for idx, login in enumerate(batch)
        ]
        data = _twitch_gql("query { " + " ".join(aliases) + " }")
        root = data.get("data") or {}
        for idx in range(len(batch)):
            user = root.get(f"u{idx}")
            if not user or not user.get("stream"):
                continue
            st = user["stream"]
            lang = (((user.get("broadcastSettings") or {}).get("language")) or "EN").upper()
            game_name = ((st.get("game") or {}).get("displayName") or "Live").strip()
            live.append({
                "id": f"twitch:{user['login'].lower()}",
                "platform": "twitch",
                "login": user["login"].lower(),
                "display_name": user.get("displayName") or user["login"],
                "url": f"https://www.twitch.tv/{user['login'].lower()}",
                "title": (st.get("title") or "").strip(),
                "game": game_name,
                "viewers": int(st.get("viewersCount") or 0),
                "language": lang,
                "thumbnail_url": st.get("previewImageURL") or "",
                "is_watchlist": True,
                "clip_ready": True,
                "recommended_asr": "hinglish" if lang in ("HI", "IN") else "whistle",
                "recommended_lang": "hi" if lang in ("HI", "IN") else "en",
            })
    return live


def _parse_views(text: str) -> int:
    if not text:
        return 0
    t = text.lower().replace(",", "").replace("watching", "").replace("views", "").strip()
    try:
        if "k" in t:
            return int(float(t.replace("k", "").strip()) * 1000)
        if "m" in t:
            return int(float(t.replace("m", "").strip()) * 1000000)
        nums = re.findall(r"\d+", t)
        return int(nums[0]) if nums else 0
    except Exception:
        return 0


def _search_youtube_live_trending(query: str = "gaming live", limit: int = 12) -> list[dict[str, Any]]:
    """Dynamically search YouTube for real-time trending live streams filtered by live status."""
    encoded_q = urllib.parse.quote_plus(query)
    url = f"https://www.youtube.com/results?search_query={encoded_q}&sp=CAMSAkAB"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    results = []
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        m = re.search(r"var ytInitialData\s*=\s*({.+?});</script>", html)
        if not m:
            return []
        data = json.loads(m.group(1))

        def find_renderers(obj):
            if isinstance(obj, dict):
                if "videoRenderer" in obj:
                    yield obj["videoRenderer"]
                for v in obj.values():
                    yield from find_renderers(v)
            elif isinstance(obj, list):
                for item in obj:
                    yield from find_renderers(item)

        seen_vids = set()
        for vr in find_renderers(data):
            vid = vr.get("videoId")
            if not vid or vid in seen_vids:
                continue
            seen_vids.add(vid)

            title = vr.get("title", {}).get("runs", [{}])[0].get("text", "")
            owner = vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "")
            view_txt = (
                vr.get("viewCountText", {}).get("runs", [{}])[0].get("text", "")
                or vr.get("viewCountText", {}).get("simpleText", "")
            )
            viewers = _parse_views(view_txt)
            if viewers < 100:  # Skip low viewer streams to avoid spam
                continue

            slug = re.sub(r"[^a-z0-9]+", "", (owner or "yt").lower())
            is_hindi = any(
                k in f"{title} {owner}".lower()
                for k in ("hindi", "bhai", "gameplay", "india", "live", "carry", "mortal", "scout", "techno")
            )

            results.append({
                "id": f"youtube:{vid}",
                "platform": "youtube",
                "login": slug,
                "display_name": owner or "YouTube Creator",
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": title,
                "game": "GTA 6" if re.search(r"gta\s*(?:6|vi)", title, flags=re.I) else (query.split()[0].title() if query else "Gaming"),
                "viewers": viewers,
                "language": "HI" if is_hindi else "EN",
                "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                "is_watchlist": False,
                "clip_ready": True,
                "recommended_asr": "hinglish" if is_hindi else "whistle",
                "recommended_lang": "hi" if is_hindi else "en",
            })
            if len(results) >= limit:
                break
    except Exception as exc:
        pass
    return results


def _probe_youtube_handle_live(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Lightweight read-only check of a YouTube creator's public /live redirect page (zero bot-bypass)."""
    handle = (entry.get("handle") or "").strip()
    if not handle:
        return None
    url = f"https://www.youtube.com/{handle}/live"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"},
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            html = resp.read(260_000).decode("utf-8", errors="ignore")
        if '"isLive":true' not in html and '"isLiveNow":true' not in html:
            return None
        m_vid = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
        if not m_vid:
            return None
        vid = m_vid.group(1)
        m_title = re.search(r'<meta\s+name="title"\s+content="([^"]+)"', html)
        title = (m_title.group(1) if m_title else f"{entry.get('name', handle)} Live").strip()
        lang = (entry.get("lang") or "EN").upper()
        slug = re.sub(r"[^a-z0-9]+", "", handle.lower())
        return {
            "id": f"youtube:{vid}",
            "platform": "youtube",
            "login": slug,
            "display_name": entry.get("name") or handle,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": title,
            "game": "GTA 6" if re.search(r"gta\s*(?:6|vi)", title, flags=re.I) else "YouTube Live",
            "viewers": 0,
            "language": lang,
            "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "is_watchlist": True,
            "clip_ready": True,
            "recommended_asr": "hinglish" if lang in ("HI", "IN") else "whistle",
            "recommended_lang": "hi" if lang in ("HI", "IN") else "en",
        }
    except Exception:
        return None


def _suggest_channel_slug(stream: dict[str, Any]) -> str:
    login = re.sub(r"[^a-z0-9]+", "-", (stream.get("login") or "live").lower()).strip("-")
    game = (stream.get("game") or "").lower()
    if "grand theft auto vi" in game or "gta 6" in game or "gta vi" in game:
        return f"{login}-gta6"
    if "valorant" in game:
        return f"{login}-valorant"
    if "minecraft" in game:
        return f"{login}-minecraft"
    return f"{login}-live"


def discover_live_streams(
    game: str | None = None,
    languages: list[str] | None = None,
    min_viewers: int = 500,
    limit: int = 16,
    include_watchlist: bool = True,
    include_youtube: bool = True,
) -> dict[str, Any]:
    """
    Discover active live streams ranked by ClipSurge virality opportunity score.
    """
    cfg = load_watchlist_config()
    target_game = game if game is not None else cfg.get("default_game", "Grand Theft Auto VI")
    target_langs = languages if languages is not None else cfg.get("default_languages", ["EN"])
    wl_set = {l.lower() for l in cfg.get("twitch_watchlist", [])}

    streams_by_id: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        f_dir = pool.submit(_fetch_twitch_directory, target_game, target_langs, max(12, limit))
        f_wl = pool.submit(_fetch_twitch_watchlist, cfg.get("twitch_watchlist", [])) if include_watchlist else None
        f_yt_trending = (
            pool.submit(
                _search_youtube_live_trending,
                f"{target_game} live" if target_game and target_game.upper() != "ALL" else "gaming live",
                limit=10,
            )
            if include_youtube
            else None
        )
        yt_futures = (
            [pool.submit(_probe_youtube_handle_live, ent) for ent in cfg.get("youtube_watchlist", [])[:8]]
            if include_youtube
            else []
        )

        try:
            for item in f_dir.result(timeout=10):
                item["is_watchlist"] = item["login"] in wl_set
                streams_by_id[item["id"]] = item
        except Exception as exc:
            errors.append(f"twitch_dir: {exc}")

        if f_wl:
            try:
                for item in f_wl.result(timeout=10):
                    # Keep watchlist live creators even if playing another game (unless game filter strictly mismatches? show them clearly!)
                    existing = streams_by_id.get(item["id"])
                    if existing:
                        existing["is_watchlist"] = True
                    else:
                        streams_by_id[item["id"]] = item
            except Exception as exc:
                errors.append(f"twitch_watchlist: {exc}")

        if f_yt_trending:
            try:
                for yt_tr in f_yt_trending.result(timeout=10):
                    if yt_tr["id"] not in streams_by_id:
                        streams_by_id[yt_tr["id"]] = yt_tr
            except Exception as exc:
                errors.append(f"yt_trending: {exc}")

        for fut in yt_futures:
            try:
                yt_item = fut.result(timeout=6)
                if yt_item:
                    streams_by_id[yt_item["id"]] = yt_item
            except Exception:
                pass

    ranked: list[dict[str, Any]] = []
    want_game_low = (target_game or "").lower()
    for st in streams_by_id.values():
        viewers = int(st.get("viewers") or 0)
        is_wl = bool(st.get("is_watchlist"))
        if st["platform"] == "twitch" and not is_wl and viewers < min_viewers:
            continue
        # Score: prioritize Twitch (most reliable live HLS) + Watchlist creators + target game + viewer count
        game_match = (want_game_low == "all") or (want_game_low in (st.get("game") or "").lower()) or (
            "grand theft auto vi" in want_game_low and ("gta 6" in (st.get("title") or "").lower() or "gta vi" in (st.get("title") or "").lower())
        )
        opp_score = 0.0
        opp_score += min(55.0, (viewers ** 0.42) * 0.9) if viewers > 0 else 25.0
        if is_wl:
            opp_score += 24.0
        if game_match:
            opp_score += 18.0
        if st["platform"] == "twitch":
            opp_score += 8.0
        st["opportunity_score"] = round(min(100.0, opp_score), 1)
        st["game_match"] = game_match
        st["suggested_channel"] = _suggest_channel_slug(st)
        ranked.append(st)

    ranked.sort(key=lambda s: (-s["opportunity_score"], -s.get("viewers", 0)))
    return {
        "discovered_at": time.time(),
        "game": target_game,
        "languages": target_langs,
        "count": len(ranked[:limit]),
        "streams": ranked[:limit],
        "preset_games": cfg.get("preset_games", ["Grand Theft Auto VI", "ALL", "Just Chatting"]),
        "errors": errors,
    }


if __name__ == "__main__":
    res = discover_live_streams()
    print(f"Found {res['count']} live streams (game={res['game']}, langs={res['languages']}):")
    for s in res["streams"][:10]:
        wl = " [WATCHLIST]" if s.get("is_watchlist") else ""
        print(
            f"  [{s['platform'].upper():7s}] {s['display_name']:<18s} | {s['viewers']:7d} viewers | "
            f"opp={s['opportunity_score']:5.1f}{wl} | {s['game']} | {s['title'][:48]}"
        )
