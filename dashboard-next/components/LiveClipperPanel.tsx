import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DiscoveredStream, LiveClipItem, LiveClipperStatus, YouTubeProfileStatus, YouTubeStatus } from "@/lib/types";
import YouTubeUploadModal from "@/components/YouTubeUploadModal";

interface Props {
  onStatusChange?: (status: LiveClipperStatus) => void;
  onOpenYouTubeTab?: () => void;
}

function parseEmbedInfo(url: string): { platform: "youtube" | "twitch" | null; embedUrl: string | null } {
  const trimmed = (url || "").trim();
  if (!trimmed) return { platform: null, embedUrl: null };
  const ytMatch = trimmed.match(/(?:youtube\.com\/watch\?.*?v=|youtu\.be\/|youtube\.com\/live\/)([a-zA-Z0-9_-]{11})/);
  if (ytMatch) {
    return {
      platform: "youtube",
      embedUrl: `https://www.youtube.com/embed/${ytMatch[1]}?autoplay=0&mute=1&rel=0`,
    };
  }
  const twMatch = trimmed.match(/twitch\.tv\/([a-zA-Z0-9_]+)/i);
  if (twMatch && !["videos", "directory", "clip"].includes(twMatch[1].toLowerCase())) {
    const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
    return {
      platform: "twitch",
      embedUrl: `https://player.twitch.tv/?channel=${twMatch[1]}&parent=${host}&muted=true`,
    };
  }
  return { platform: null, embedUrl: null };
}

function latestTierChip(tier: string) {
  const t = (tier || "").toUpperCase();
  if (t.startsWith("S")) return "chip chip-accent";
  if (t.startsWith("A")) return "chip chip-warn";
  if (t.startsWith("B")) return "chip chip-info";
  return "chip chip-neutral";
}

export default function LiveClipperPanel({ onStatusChange, onOpenYouTubeTab }: Props) {
  const [data, setData] = useState<LiveClipperStatus | null>(null);
  const [url, setUrl] = useState("https://www.youtube.com/watch?v=LMbea5SozeM");
  const [name, setName] = useState("mythpat-gta6");
  const [keywords, setKeywords] = useState("gta 6,vice city,lucia,jason,police,wasted,insane,bhai,arey,clip");
  const [threshold, setThreshold] = useState(72);
  const [chatPrePad, setChatPrePad] = useState(20);
  const [postPad, setPostPad] = useState(8);
  const [maxClipSec, setMaxClipSec] = useState(30);
  const [layout, setLayout] = useState<"split-blur" | "facecam-split" | "pip-overlay" | "crop" | "landscape">("split-blur");
  const [facecamPos, setFacecamPos] = useState<"top-right" | "top-left" | "bottom-right" | "bottom-left">("top-right");
  const [asr, setAsr] = useState<"modal" | "hinglish" | "whisper" | "whistle">("whistle");
  const [asrLang, setAsrLang] = useState<"auto" | "hi" | "en">("en");
  const [autoUpload, setAutoUpload] = useState(false);
  const [uploadPrivacy, setUploadPrivacy] = useState<"private" | "unlisted" | "public">("private");
  const [clipperYt, setClipperYt] = useState<YouTubeProfileStatus | null>(null);
  const [uploadClip, setUploadClip] = useState<LiveClipItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [selectedClipKey, setSelectedClipKey] = useState<string | null>(null);
  const [clipSort, setClipSort] = useState<"tier_desc" | "tier_asc" | "score_desc" | "newest">("tier_desc");
  const [tierFilter, setTierFilter] = useState<"ALL" | "S-TIER" | "A-TIER" | "B-TIER" | "REVIEW">("ALL");
  const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);

  // Live Stream Scout & Parallel Auto-Clipper state
  const [scoutGame, setScoutGame] = useState("Grand Theft Auto VI");
  const [scoutLang, setScoutLang] = useState("EN");
  const [scoutMaxParallel, setScoutMaxParallel] = useState(2);
  const [scoutStreams, setScoutStreams] = useState<DiscoveredStream[]>([]);
  const [scoutLoading, setScoutLoading] = useState(false);
  const [scoutBusy, setScoutBusy] = useState(false);
  const [scoutNotice, setScoutNotice] = useState<string | null>(null);
  const [batchReviewing, setBatchReviewing] = useState(false);
  const [humanReviewingKey, setHumanReviewingKey] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);
  const initializedFromState = useRef(false);

  const pollStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/clipper/status");
      if (!res.ok) return;
      const json: LiveClipperStatus = await res.json();
      setData(json);
      onStatusChange?.(json);
      if (!initializedFromState.current && json.state?.url) {
        setUrl(json.state.url);
        if (json.state.channel) setName(json.state.channel);
        if (json.state.threshold) setThreshold(Math.max(72, Number(json.state.threshold)));
        if (json.state.chat_pre_pad) setChatPrePad(json.state.chat_pre_pad);
        if (json.state.post_pad) setPostPad(json.state.post_pad);
        initializedFromState.current = true;
      }
    } catch {
      // handled silently between polls
    }
  }, [onStatusChange]);

  useEffect(() => {
    pollStatus();
    const id = setInterval(pollStatus, 2500);
    return () => clearInterval(id);
  }, [pollStatus]);

  useEffect(() => {
    let active = true;
    const pollYt = async () => {
      try {
        const res = await fetch("/api/youtube/status?profile=clipper");
        if (!res.ok) return;
        const json: YouTubeStatus = await res.json();
        if (active) setClipperYt(json.profiles?.clipper || null);
      } catch {
        // ignore transient poll errors
      }
    };
    pollYt();
    const id = setInterval(pollYt, 5000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    logRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [data?.logs?.length]);

  const sessions = data?.sessions || [];
  const activeSession = useMemo(() => {
    if (!sessions.length) return null;
    if (selectedSession) {
      const found = sessions.find((s) => s.channel === selectedSession);
      if (found) return found;
    }
    return sessions[0];
  }, [sessions, selectedSession]);

  const activeUrl = activeSession?.state?.url || (data?.running && data.state?.url ? data.state.url : url);
  const embed = useMemo(() => parseEmbedInfo(activeUrl), [activeUrl]);

  const clips = data?.clips || [];
  const tierRank = (tier: string): number => {
    const t = (tier || "").toUpperCase();
    if (t.startsWith("S")) return 3;
    if (t.startsWith("A")) return 2;
    if (t.startsWith("B")) return 1;
    return 0;
  };

  const tierCounts = useMemo(() => {
    const counts = { ALL: clips.length, "S-TIER": 0, "A-TIER": 0, "B-TIER": 0, REVIEW: 0 };
    for (const c of clips) {
      const t = (c.tier || "").toUpperCase();
      if (t === "S-TIER") counts["S-TIER"] += 1;
      else if (t === "A-TIER") counts["A-TIER"] += 1;
      else if (t === "B-TIER") counts["B-TIER"] += 1;
      if (c.needs_human_review) counts.REVIEW += 1;
    }
    return counts;
  }, [clips]);

  const sortedClips = useMemo(() => {
    const filtered =
      tierFilter === "ALL"
        ? [...clips]
        : tierFilter === "REVIEW"
          ? clips.filter((c) => c.needs_human_review)
          : clips.filter((c) => (c.tier || "").toUpperCase() === tierFilter);
    filtered.sort((a, b) => {
      if (clipSort === "tier_desc") {
        const diff = tierRank(b.tier) - tierRank(a.tier);
        if (diff !== 0) return diff;
        if (b.total_score !== a.total_score) return b.total_score - a.total_score;
        return (b.mtime || 0) - (a.mtime || 0);
      }
      if (clipSort === "tier_asc") {
        const diff = tierRank(a.tier) - tierRank(b.tier);
        if (diff !== 0) return diff;
        if (a.total_score !== b.total_score) return a.total_score - b.total_score;
        return (b.mtime || 0) - (a.mtime || 0);
      }
      if (clipSort === "score_desc") {
        if (b.total_score !== a.total_score) return b.total_score - a.total_score;
        return (b.mtime || 0) - (a.mtime || 0);
      }
      return (b.mtime || 0) - (a.mtime || 0);
    });
    return filtered;
  }, [clips, clipSort, tierFilter]);

  const selectedClip: LiveClipItem | null = useMemo(() => {
    if (!sortedClips.length) return null;
    if (selectedClipKey) {
      const found = sortedClips.find((c) => `${c.channel}/${c.clip_id}` === selectedClipKey);
      if (found) return found;
    }
    return sortedClips[0];
  }, [sortedClips, selectedClipKey]);

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/clipper/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          name,
          keywords,
          threshold,
          chat_pre_pad: chatPrePad,
          post_pad: postPad,
          max_clip_sec: maxClipSec,
          layout,
          facecam_pos: facecamPos,
          asr,
          asr_lang: asrLang,
          auto_upload: autoUpload,
          upload_privacy: uploadPrivacy,
          upload_profile: "clipper",
          continuous: true,
          max_clips: 0,
          duration_minutes: 0,
          keep_max_clips: 20,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed to start live clipper");
      if (json.channel) setSelectedSession(json.channel);
      await pollStatus();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to start");
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async (channel?: string) => {
    setBusy(true);
    setErr(null);
    try {
      await fetch("/api/clipper/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(channel ? { channel } : {}),
      });
      await pollStatus();
    } finally {
      setBusy(false);
    }
  };

  const handleToggleApprove = async (clip: LiveClipItem) => {
    await fetch("/api/clipper/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        channel: clip.channel,
        clip_id: clip.clip_id,
        approved: !clip.human_approved,
      }),
    });
    await pollStatus();
  };

  const handleDeleteClip = async (clip: LiveClipItem) => {
    const key = `${clip.channel}/${clip.clip_id}`;
    if (confirmDeleteKey !== key) {
      setConfirmDeleteKey(key);
      return;
    }
    setDeletingKey(key);
    try {
      const res = await fetch("/api/clipper/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel: clip.channel, clip_id: clip.clip_id }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        setErr(j.error || "Failed to delete clip");
      } else {
        setConfirmDeleteKey(null);
        if (selectedClipKey === key) setSelectedClipKey(null);
        setScoutNotice("Clip moved to trash (exports/live-clips-deleted) — it can still be restored.");
        await pollStatus();
      }
    } finally {
      setDeletingKey(null);
    }
  };

  const handleDiscoverStreams = useCallback(async (gameOverride?: string, langOverride?: string) => {
    setScoutLoading(true);
    setScoutNotice(null);
    try {
      const g = encodeURIComponent(gameOverride ?? scoutGame);
      const l = encodeURIComponent(langOverride ?? scoutLang);
      const res = await fetch(`/api/clipper/discover?game=${g}&lang=${l}&limit=12`);
      const json = await res.json();
      if (res.ok && Array.isArray(json.streams)) {
        setScoutStreams(json.streams);
      } else {
        setScoutNotice(json.error || "Discovery failed");
      }
    } catch {
      setScoutNotice("Could not reach discovery endpoint");
    } finally {
      setScoutLoading(false);
    }
  }, [scoutGame, scoutLang]);

  useEffect(() => {
    handleDiscoverStreams("Grand Theft Auto VI", "EN");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleClipDiscovered = async (stream: DiscoveredStream) => {
    setScoutBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/clipper/start-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          streams: [stream],
          max_parallel: 4,
          threshold,
          max_clip_sec: maxClipSec,
          layout,
          auto_upload: autoUpload,
          upload_privacy: uploadPrivacy,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed to start clip session");
      setScoutNotice(`Started clipping ${stream.display_name} (@${stream.suggested_channel})`);
      setSelectedSession(stream.suggested_channel);
      await Promise.all([pollStatus(), handleDiscoverStreams()]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to start stream");
    } finally {
      setScoutBusy(false);
    }
  };

  const handleAutoClipTopN = async () => {
    setScoutBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/clipper/start-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          game: scoutGame,
          lang: scoutLang,
          max_parallel: scoutMaxParallel,
          threshold,
          max_clip_sec: maxClipSec,
          layout,
          auto_upload: autoUpload,
          upload_privacy: uploadPrivacy,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Parallel batch start failed");
      const startedNames = (json.started || []).map((s: { display_name?: string; channel: string }) => s.display_name || s.channel);
      setScoutNotice(
        startedNames.length
          ? `Started ${startedNames.length} parallel clipper(s): ${startedNames.join(", ")}`
          : `All ${json.max_parallel} parallel slots are already active.`
      );
      await Promise.all([pollStatus(), handleDiscoverStreams()]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Parallel start failed");
    } finally {
      setScoutBusy(false);
    }
  };

  const handleToggleAutoScout = async () => {
    const nextEnabled = !Boolean(data?.auto_scout?.enabled);
    setScoutBusy(true);
    try {
      const res = await fetch("/api/clipper/auto-scout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: nextEnabled,
          game: scoutGame,
          lang: scoutLang,
          max_parallel: scoutMaxParallel,
          threshold,
          max_clip_sec: maxClipSec,
          layout,
          poll_interval_sec: 120,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Auto-Scout toggle failed");
      setScoutNotice(
        nextEnabled
          ? `Auto-Scout ON — scanning ${scoutGame} every 2 min (up to ${scoutMaxParallel} parallel streams)`
          : "Auto-Scout paused."
      );
      await pollStatus();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Auto-Scout failed");
    } finally {
      setScoutBusy(false);
    }
  };

  const handleBatchReview = async () => {
    setBatchReviewing(true);
    setErr(null);
    try {
      const res = await fetch("/api/clipper/batch-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ batch_size: 3 }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Batch review failed");
      setScoutNotice(
        json.reviewed_count > 0
          ? `Groq Batch-Reviewed ${json.reviewed_count} clip(s) in 1 API call (tiers re-scored & titles cached)`
          : "All clips already have cached Groq reviews (0 API calls used)."
      );
      await pollStatus();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Batch review failed");
    } finally {
      setBatchReviewing(false);
    }
  };

  const handleHumanReview = async (clip?: LiveClipItem) => {
    const key = clip ? `${clip.channel}/${clip.clip_id}` : "__s_tier__";
    setHumanReviewingKey(key);
    setErr(null);
    try {
      const res = await fetch("/api/clipper/human-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(clip ? { channel: clip.channel, clip_id: clip.clip_id, force: true } : { limit: 3 }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Human Reviewer failed");
      if (clip && json.reviews?.[0]) {
        const r = json.reviews[0];
        setScoutNotice(`Human Reviewer (${r.model}): ${r.verdict} (${r.human_score}/100) — "${r.gut_reaction}"`);
      } else {
        setScoutNotice(
          json.reviewed_count > 0
            ? `Human Reviewer evaluated ${json.reviewed_count} A/S-tier clip(s).`
            : "No unreviewed A-Tier or S-Tier clips waiting — every exported clip is already reviewed."
        );
      }
      await pollStatus();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Human Reviewer failed");
    } finally {
      setHumanReviewingKey(null);
    }
  };

  const st = activeSession?.state || data?.state || null;
  const latest = st?.latest_segment || null;
  const inProgress = st?.in_progress_clips || [];
  const history = st?.history || [];
  const running = Boolean(activeSession ? activeSession.running : data?.running);
  const runningCount = data?.running_count ?? (data?.running ? 1 : 0);

const autoScoutOn = Boolean(data?.auto_scout?.enabled);

  return (
    <div className="space-y-5">
      {/* Live stream scout */}
      <section className="panel">
        <div className="panel-head">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="panel-title">Live stream scout</h2>
              {autoScoutOn && (
                <span className="chip chip-ok">
                  <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-[#7fc8a3]" />
                  Auto-scout · {data?.auto_scout?.max_parallel}×
                </span>
              )}
            </div>
            <p className="panel-sub">
              Finds live streams worth clipping and opens parallel sessions without local GPU time.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="scout-game">
              Game
            </label>
            <div className="w-[156px]">
              <select
                id="scout-game"
                value={scoutGame}
                onChange={(e) => {
                  setScoutGame(e.target.value);
                  handleDiscoverStreams(e.target.value, scoutLang);
                }}
                className="select h-8 text-[11.5px]"
              >
                <option value="Grand Theft Auto VI">GTA VI (GTA 6)</option>
                <option value="ALL">Top All Games</option>
                <option value="Just Chatting">Just Chatting</option>
                <option value="Grand Theft Auto V">GTA V</option>
                <option value="VALORANT">VALORANT</option>
                <option value="Minecraft">Minecraft</option>
                <option value="Fortnite">Fortnite</option>
              </select>
            </div>

            <label className="sr-only" htmlFor="scout-lang">
              Language
            </label>
            <div className="w-[116px]">
              <select
                id="scout-lang"
                value={scoutLang}
                onChange={(e) => {
                  setScoutLang(e.target.value);
                  handleDiscoverStreams(scoutGame, e.target.value);
                }}
                className="select h-8 text-[11.5px]"
              >
                <option value="EN">English</option>
                <option value="ALL">All languages</option>
              </select>
            </div>

            <label className="sr-only" htmlFor="scout-parallel">
              Parallel streams
            </label>
            <div className="w-[112px]">
              <select
                id="scout-parallel"
                value={scoutMaxParallel}
                onChange={(e) => setScoutMaxParallel(Number(e.target.value))}
                title="Simultaneous parallel streams"
                className="select h-8 text-[11.5px]"
              >
                <option value={2}>2 parallel</option>
                <option value={3}>3 parallel</option>
                <option value={4}>4 parallel</option>
              </select>
            </div>

            <button
              type="button"
              disabled={scoutLoading}
              onClick={() => handleDiscoverStreams()}
              className="btn btn-sm btn-secondary"
            >
              {scoutLoading ? "Scanning" : "Scan live"}
            </button>

            <button
              type="button"
              disabled={scoutBusy}
              onClick={handleAutoClipTopN}
              className="btn btn-sm btn-primary"
            >
              Auto-clip top {scoutMaxParallel}
            </button>

            <button
              type="button"
              disabled={scoutBusy}
              onClick={handleToggleAutoScout}
              aria-pressed={autoScoutOn}
              className={`btn btn-sm ${autoScoutOn ? "btn-secondary text-[#9ed6b8]" : "btn-ghost border border-[#222936]"}`}
            >
              {autoScoutOn ? "Auto-scout on" : "Auto-scout off"}
            </button>
          </div>
        </div>

        <div className="space-y-3.5 p-5">
          {scoutNotice && (
            <div className="rounded-xl border border-[#7fc8a3]/25 bg-[#7fc8a3]/08 px-3.5 py-2.5 font-mono text-[11px] leading-relaxed text-[#9ed6b8]">
              {scoutNotice}
            </div>
          )}

          {scoutStreams.length > 0 ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {scoutStreams.slice(0, 8).map((item) => {
                const isLiveClip =
                  item.already_clipping ||
                  sessions.some(
                    (s) =>
                      s.running &&
                      (s.channel.toLowerCase() === item.suggested_channel.toLowerCase() ||
                        (s.state.url || "").toLowerCase().replace(/\/$/, "") ===
                          item.url.toLowerCase().replace(/\/$/, ""))
                  );
                return (
                  <div
                    key={item.id}
                    className={`flex flex-col overflow-hidden rounded-xl border bg-[#0b0e13] ${
                      isLiveClip ? "border-[#7fc8a3]/45" : "border-[#1a1f28]"
                    }`}
                  >
                    <div className="relative aspect-video bg-black">
                      {item.thumbnail_url && (
                        <img
                          src={item.thumbnail_url}
                          alt={item.display_name}
                          className="h-full w-full object-cover"
                        />
                      )}
                      <span className="absolute left-2 top-2 rounded bg-[#c96f6f] px-1.5 py-0.5 font-mono text-[9.5px] font-semibold tracking-wide text-white">
                        LIVE
                      </span>
                      {item.viewers > 0 && (
                        <span className="absolute right-2 top-2 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[9.5px] text-[#ecebe6]">
                          {(item.viewers / 1000).toFixed(1)}K
                        </span>
                      )}
                      <span className="absolute bottom-2 right-2 rounded bg-black/72 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-[#a3a099]">
                        {item.platform} · {item.language}
                      </span>
                      {item.is_watchlist && (
                        <span className="absolute bottom-2 left-2 rounded bg-[#dbb675] px-1.5 py-0.5 font-mono text-[9px] font-semibold text-[#17100c]">
                          Watchlist
                        </span>
                      )}
                    </div>
                    <div className="flex flex-1 flex-col justify-between gap-2.5 p-3">
                      <div className="min-w-0">
                        <p className="truncate text-[12.5px] font-medium text-[#ecebe6]">
                          {item.display_name}
                        </p>
                        <p className="mt-0.5 line-clamp-1 text-[11px] text-[#79776f]" title={item.title}>
                          {item.title || item.game}
                        </p>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-[10px] text-[#79776f]">{item.game}</span>
                        {isLiveClip ? (
                          <span className="chip chip-ok shrink-0">
                            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-[#7fc8a3]" />
                            Clipping
                          </span>
                        ) : (
                          <button
                            type="button"
                            disabled={scoutBusy}
                            onClick={() => handleClipDiscovered(item)}
                            className="btn btn-xs btn-secondary shrink-0"
                          >
                            Clip stream
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-[#222936] px-4 py-10 text-center text-[11.5px] leading-relaxed text-[#79776f]">
              {scoutLoading
                ? "Scanning live platforms for GTA VI streams."
                : "No live streams found for this filter. Pick another game or scan again."}
            </div>
          )}
        </div>
      </section>

      {/* Active sessions */}
      {sessions.length > 0 && (
        <section className="panel px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-[10px] font-medium uppercase tracking-[0.12em] text-[#79776f]">
              Sessions · {runningCount} live
            </span>
            {sessions.map((s) => {
              const isSel = activeSession?.channel === s.channel;
              return (
                <div
                  key={s.channel}
                  className={`inline-flex items-center gap-1.5 rounded-lg border pl-2.5 pr-1.5 py-1 ${
                    isSel
                      ? "border-[#e5a183]/45 bg-[#e5a183]/09"
                      : "border-[#222936] bg-[#0b0e13]"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedSession(s.channel)}
                    className="inline-flex items-center gap-2 font-mono text-[11px] text-[#d8d4cb]"
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        s.running ? "pulse-dot bg-[#e08a8a]" : "bg-[#3a3936]"
                      }`}
                    />
                    @{s.channel}
                    <span className="text-[10px] text-[#79776f]">{s.state.segments_scanned} segs</span>
                  </button>
                  {s.running && (
                    <button
                      type="button"
                      title={`Stop @${s.channel}`}
                      onClick={() => handleStop(s.channel)}
                      className="rounded px-1.5 py-0.5 text-[10px] text-[#79776f] transition-colors hover:bg-[#e08a8a]/12 hover:text-[#e9aaaa]"
                    >
                      Stop
                    </button>
                  )}
                </div>
              );
            })}
            {runningCount > 1 && (
              <button
                type="button"
                onClick={() => handleStop()}
                className="btn btn-xs btn-danger ml-auto"
              >
                Stop all
              </button>
            )}
          </div>
        </section>
      )}

      {/* Clipper control */}
      <section className="panel">
        <div className="panel-head">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  running ? "live-ring bg-[#e08a8a]" : "bg-[#3a3936]"
                }`}
              />
              <h2 className="panel-title">Live stream clipper</h2>
              <span className="chip chip-neutral font-mono">
                {running ? st?.status || "Listening live" : "Idle"}
              </span>
            </div>
            <p className="panel-sub">
              Paste a Twitch or YouTube URL. Add a second URL with a new channel label to clip both at once.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={busy || !url.trim()}
              onClick={handleStart}
              className="btn btn-sm btn-primary"
            >
              {busy ? "Connecting" : runningCount > 0 ? "Add stream" : "Start clipper"}
            </button>
            {running && activeSession && (
              <button
                type="button"
                disabled={busy}
                onClick={() => handleStop(activeSession.channel)}
                className="btn btn-sm btn-danger"
              >
                {busy ? "Stopping" : `Stop @${activeSession.channel}`}
              </button>
            )}
          </div>
        </div>

        <form onSubmit={handleStart} className="space-y-4 p-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-6 lg:grid-cols-12">
            <div className="field sm:col-span-4 lg:col-span-6">
              <label className="label" htmlFor="clip-url">
                Stream URL
              </label>
              <input
                id="clip-url"
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://youtube.com/watch?v=... or https://twitch.tv/..."
                className="input font-mono text-[11.5px]"
              />
            </div>

            <div className="field sm:col-span-2 lg:col-span-3">
              <label className="label" htmlFor="clip-name">
                Channel label
              </label>
              <input
                id="clip-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="mythpat-gta6"
                className="input font-mono text-[11.5px]"
              />
            </div>

            <div className="field sm:col-span-2 lg:col-span-1">
              <label className="label" htmlFor="clip-max">
                Max sec
              </label>
              <input
                id="clip-max"
                type="number"
                min={15}
                max={60}
                value={maxClipSec}
                onChange={(e) => setMaxClipSec(Number(e.target.value))}
                className="input font-mono"
              />
            </div>

            <div className="field sm:col-span-2 lg:col-span-2">
              <label className="label" htmlFor="clip-layout">
                Framing
              </label>
              <select
                id="clip-layout"
                value={layout}
                onChange={(e) =>
                  setLayout(
                    e.target.value as "facecam-split" | "pip-overlay" | "split-blur" | "crop" | "landscape"
                  )
                }
                className="select"
              >
                <option value="split-blur">9:16 split-blur</option>
                <option value="facecam-split">9:16 zero-gap facecam</option>
                <option value="pip-overlay">9:16 floating facecam</option>
                <option value="crop">9:16 center crop</option>
                <option value="landscape">16:9 landscape</option>
              </select>
            </div>

            <div className="field sm:col-span-2 lg:col-span-2">
              <label className="label" htmlFor="clip-facecam">
                Facecam corner
              </label>
              <select
                id="clip-facecam"
                value={facecamPos}
                disabled={layout !== "facecam-split" && layout !== "pip-overlay"}
                onChange={(e) =>
                  setFacecamPos(
                    e.target.value as "top-right" | "top-left" | "bottom-right" | "bottom-left"
                  )
                }
                className="select"
              >
                <option value="top-right">Top right</option>
                <option value="top-left">Top left</option>
                <option value="bottom-right">Bottom right</option>
                <option value="bottom-left">Bottom left</option>
              </select>
            </div>

            <div className="field sm:col-span-3 lg:col-span-4">
              <label className="label" htmlFor="clip-asr">
                Speech engine
              </label>
              <select
                id="clip-asr"
                value={asr}
                onChange={(e) => setAsr(e.target.value as "modal" | "hinglish" | "whisper" | "whistle")}
                className="select"
              >
                <option value="modal">Modal cloud GPU · free T4</option>
                <option value="hinglish">Local Whisper Hinglish · RTX 4060</option>
                <option value="whisper">Local Whisper small · RTX 4060</option>
                <option value="whistle">Local Cactus Whistle · 16.9MB CPU</option>
              </select>
            </div>

            <div className="field sm:col-span-3 lg:col-span-2">
              <label className="label" htmlFor="clip-lang">
                Language
              </label>
              <select
                id="clip-lang"
                value={asrLang}
                onChange={(e) => setAsrLang(e.target.value as "auto" | "hi" | "en")}
                className="select"
              >
                <option value="auto">Auto detect</option>
                <option value="hi">Hindi</option>
                <option value="en">English</option>
              </select>
            </div>

            <div className="field sm:col-span-6 lg:col-span-4">
              <label className="label" htmlFor="clip-keywords">
                Extra keywords
              </label>
              <input
                id="clip-keywords"
                type="text"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                className="input font-mono text-[11.5px]"
              />
              <p className="hint">About 160 more phrases live in the clipper config.</p>
            </div>

            <div className="field sm:col-span-6 lg:col-span-2">
              <label className="label" htmlFor="clip-threshold">
                Trigger score · {threshold}
              </label>
              <input
                id="clip-threshold"
                type="range"
                min={72}
                max={85}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                className="mt-2.5 w-full"
              />
              <p className="hint">Minimum 72, the A-tier export gate.</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#1a1f28] pt-3.5">
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex cursor-pointer items-center gap-2 text-[12px] text-[#d8d4cb]">
                <input
                  type="checkbox"
                  checked={autoUpload}
                  onChange={(e) => setAutoUpload(e.target.checked)}
                />
                Auto-upload S-tier clips (90+) to the clipper channel
              </label>

              {clipperYt?.connected && clipperYt.channel ? (
                <span className="chip chip-ok">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#7fc8a3]" />
                  {clipperYt.channel.title}
                </span>
              ) : (
                <button type="button" onClick={() => onOpenYouTubeTab?.()} className="btn btn-xs btn-danger">
                  Connect clipper channel
                </button>
              )}
            </div>

            {autoUpload && (
              <div className="flex items-center gap-2">
                <label className="label mb-0" htmlFor="clip-privacy">
                  Visibility
                </label>
                <div className="w-[214px]">
                  <select
                    id="clip-privacy"
                    value={uploadPrivacy}
                    onChange={(e) =>
                      setUploadPrivacy(e.target.value as "private" | "unlisted" | "public")
                    }
                    className="select h-8 text-[11.5px]"
                  >
                    <option value="private">Private draft · safe</option>
                    <option value="unlisted">Unlisted</option>
                    <option value="public">Public immediately</option>
                  </select>
                </div>
              </div>
            )}
          </div>

          {err && (
            <div className="rounded-xl border border-[#e08a8a]/30 bg-[#e08a8a]/08 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-[#e9aaaa]">
              {err}
            </div>
          )}
        </form>
      </section>

      {/* Live pulse */}
      <section className="panel overflow-hidden">
        <div className="grid grid-cols-2 gap-px bg-[#1a1f28] sm:grid-cols-3 lg:grid-cols-5">
          <MetricBox
            label="Live status"
            value={running ? "Live" : "Idle"}
            sub={st?.channel ? `@${st.channel}` : "Paste a URL to start"}
            tone={running ? "danger" : "muted"}
          />
          <MetricBox
            label="Segments scanned"
            value={`${st?.segments_scanned ?? 0}`}
            sub={`${(((st?.segments_scanned ?? 0) * 10) / 60).toFixed(1)} min analyzed`}
          />
          <MetricBox
            label="Clips in progress"
            value={`${inProgress.length}`}
            sub={inProgress.length ? inProgress[0].stage.replace("_", " ") : "Waiting for a spike"}
            tone={inProgress.length > 0 ? "warn" : "muted"}
          />
          <MetricBox
            label="Clips created"
            value={`${clips.length}`}
            sub={`${clips.filter((c) => c.human_approved).length} human approved`}
            tone="ok"
          />
          <MetricBox
            label="Chat velocity"
            value={latest?.chat?.ratio ? `${latest.chat.ratio.toFixed(1)}×` : "None"}
            sub={
              latest?.chat?.msgs_in_window !== undefined
                ? `${latest.chat.msgs_in_window} msgs / 10s · ${latest.chat.unique_authors ?? 0} users`
                : "Chat monitor standby"
            }
            tone={latest?.chat?.is_explosion ? "accent" : "muted"}
          />
        </div>
      </section>

      {/* Monitor + signals */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <section className="panel flex flex-col overflow-hidden lg:col-span-7">
          <div className="flex items-center justify-between gap-3 border-b border-[#1a1f28] px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-[#79776f]">
                Live stream monitor
              </span>
              {embed.platform && <span className="chip chip-neutral font-mono uppercase">{embed.platform}</span>}
            </div>
            {activeUrl && (
              <a
                href={activeUrl}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-[10.5px] text-[#9dbbcf] hover:underline"
              >
                Open original ↗
              </a>
            )}
          </div>

          <div className="relative aspect-video bg-black">
            {embed.embedUrl ? (
              <iframe
                src={embed.embedUrl}
                title="Live stream player"
                className="h-full w-full border-0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center px-6 text-center text-[11.5px] leading-relaxed text-[#79776f]">
                Paste a live YouTube or Twitch URL above to preview the stream here.
              </div>
            )}
          </div>

          <div className="space-y-2 border-t border-[#1a1f28] p-4">
            <div className="flex items-center justify-between font-mono text-[10.5px] text-[#79776f]">
              <span>Virality timeline · last {history.length} windows</span>
              <span>Trigger {st?.threshold ?? threshold}</span>
            </div>
            <div className="relative flex h-24 items-end gap-1 overflow-hidden rounded-xl border border-[#1a1f28] bg-[#0b0e13] px-2 pb-1 pt-3">
              <div
                className="pointer-events-none absolute left-0 right-0 border-t border-dashed border-[#e5a183]/55"
                style={{ bottom: `${Math.min(95, st?.threshold ?? threshold)}%` }}
              />
              {history.length === 0 ? (
                <div className="flex h-full w-full items-center justify-center font-mono text-[11px] text-[#79776f]">
                  Waiting for the first ten-second window
                </div>
              ) : (
                history.map((pt) => (
                  <div
                    key={`${pt.idx}-${pt.time}`}
                    title={`[${pt.time}] seg_${pt.idx} · ${pt.total}/100 · chat ${pt.chat} · audio ${pt.audio} · visual ${pt.visual} · text ${pt.txt}`}
                    className="min-w-[6px] flex-1 rounded-t-[2px] transition-all"
                    style={{
                      height: `${Math.max(5, Math.min(100, pt.total))}%`,
                      backgroundColor: pt.triggered
                        ? "#e5a183"
                        : pt.total >= (st?.threshold ?? threshold) * 0.7
                          ? "#dbb675"
                          : "#3d4757",
                    }}
                  />
                ))
              )}
            </div>
          </div>
        </section>

        <div className="flex flex-col gap-4 lg:col-span-5">
          <div className="panel p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-[#79776f]">
                Multimodal signal radar
              </span>
              {latest && (
                <span className={`chip ${latestTierChip(latest.tier)}`}>
                  {latest.tier} · {latest.total_score}/100
                </span>
              )}
            </div>

            <div className="mt-3.5 space-y-3">
              <SignalBar label="Chat explosion" value={latest?.chat?.score ?? 0} max={55} color="#e5a183" />
              <SignalBar label="Audio emotion" value={latest?.audio?.score ?? 0} max={35} color="#dbb675" />
              <SignalBar
                label="Transcript hype"
                value={latest?.transcript_score?.score ?? 0}
                max={40}
                color="#9dbbcf"
              />
              <SignalBar
                label="Visual action"
                value={latest?.visual?.score ?? 0}
                max={32}
                color="#8e8b84"
              />
            </div>

            <div className="mt-3 border-t border-[#1a1f28] pt-2.5">
              <div className="flex items-start justify-between gap-3 font-mono text-[10.5px]">
                <span className="text-[#79776f]">Cross-modal synergy</span>
                <span
                  className={`text-right ${
                    (latest?.synergy ?? 0) > 0
                      ? "text-[#9ed6b8]"
                      : (latest?.synergy ?? 0) < 0
                        ? "text-[#e9aaaa]"
                        : "text-[#79776f]"
                  }`}
                >
                  {(latest?.synergy ?? 0) >= 0 ? `+${latest?.synergy ?? 0}` : latest?.synergy}
                  {latest?.synergy_reasons?.length ? ` (${latest.synergy_reasons.join(", ")})` : ""}
                </span>
              </div>
            </div>

            {latest?.transcript && (
              <div className="panel-inset mt-3 p-2.5">
                <p className="mb-1 font-mono text-[9.5px] uppercase tracking-[0.1em] text-[#79776f]">
                  Segment {latest.time} · {latest.archetype}
                </p>
                <p className="font-mono text-[11px] leading-relaxed text-[#a3a099]">
                  &ldquo;{latest.transcript}&rdquo;
                </p>
              </div>
            )}
          </div>

          <div className="panel p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-[#79776f]">
                In-progress queue · {inProgress.length}
              </span>
              <span className="font-mono text-[10px] text-[#79776f]">NVENC</span>
            </div>
            {inProgress.length === 0 ? (
              <p className="mt-3 font-mono text-[11px] leading-relaxed text-[#79776f]">
                Nothing rendering. Trigger threshold is {st?.threshold ?? threshold}/100.
              </p>
            ) : (
              <div className="mt-3 space-y-2">
                {inProgress.map((job, idx) => (
                  <div
                    key={`${job.trigger_idx}-${idx}`}
                    className="flex items-center justify-between gap-2 rounded-lg border border-[#dbb675]/30 bg-[#dbb675]/08 px-3 py-2.5 text-[11.5px]"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-[#e6c894]">
                        {job.stage === "EXPORTING_NVENC" ? "Rendering NVENC 9:16" : "Collecting post-pad reaction"}
                      </p>
                      <p className="font-mono text-[10.5px] text-[#a3a099]">
                        {job.archetype} · {job.score}/100 · seg_{job.trigger_idx}
                      </p>
                    </div>
                    <span className="pulse-dot h-2 w-2 shrink-0 rounded-full bg-[#dbb675]" />
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="panel flex min-h-[150px] flex-1 flex-col overflow-hidden">
            <div className="flex items-center justify-between gap-2 border-b border-[#1a1f28] px-3.5 py-2">
              <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-[#79776f]">
                Clipper feed
              </span>
              <span className="font-mono text-[10px] text-[#79776f]">{data?.logs?.length ?? 0} lines</span>
            </div>
            <div className="h-40 space-y-1 overflow-y-auto p-3 font-mono text-[10.5px] leading-relaxed">
              {(data?.logs?.length
                ? data.logs
                : ["Start a stream to see ten-second window scores here."]
              ).map((line, i) => (
                <div
                  key={i}
                  className={
                    line.includes("EXPORTED") || line.includes("SAVED")
                      ? "text-[#9ed6b8]"
                      : line.includes("LIVE MOMENT") ||
                          line.includes("CLIP TRIGGERED") ||
                          line.includes("ESCALATING")
                        ? "text-[#e6c894]"
                        : line.includes("error") || line.includes("failed")
                          ? "text-[#e9aaaa]"
                          : "text-[#79776f]"
                  }
                >
                  {line}
                </div>
              ))}
              <div ref={logRef} />
            </div>
          </div>
        </div>
      </div>

      {/* Created clips */}
      <section className="panel">
        <div className="panel-head">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="panel-title">Created clips</h2>
              <span className="chip chip-neutral font-mono">{clips.length}</span>
              <span className="chip chip-accent">S-tier is 90+</span>
              {data?.groq_usage?.configured && (
                <span className="chip chip-ok font-mono">
                  Groq {data.groq_usage.llm_calls_today + data.groq_usage.whisper_calls_today}/
                  {data.groq_usage.rpd_soft_cap} · {data.groq_usage.calls_saved} saved
                </span>
              )}
            </div>
            <p className="panel-sub">
              Saved under{" "}
              <code className="font-mono text-[11px] text-[#a3a099]">exports/live-clips/</code> with captions
              and Blueprint v2 scoring.
            </p>
          </div>
          <button type="button" onClick={pollStatus} className="btn btn-xs btn-ghost">
            Refresh
          </button>
        </div>

        <div className="space-y-3.5 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={batchReviewing}
                onClick={handleBatchReview}
                className="btn btn-xs btn-secondary"
                title="Score and title up to three unreviewed clips in one Groq call"
              >
                {batchReviewing ? "Batching" : "Batch review 3 · 1 call"}
              </button>
              <button
                type="button"
                disabled={humanReviewingKey === "__s_tier__"}
                onClick={() => handleHumanReview()}
                className="btn btn-xs btn-secondary"
                title="Run the normal-viewer review agent on unreviewed A and S tier clips"
              >
                {humanReviewingKey === "__s_tier__" ? "Reviewing" : "Review A/S clips"}
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="seg">
                {(["ALL", "S-TIER", "A-TIER", "B-TIER", "REVIEW"] as const).map((tierKey) => (
                  <button
                    key={tierKey}
                    type="button"
                    aria-pressed={tierFilter === tierKey}
                    onClick={() => setTierFilter(tierKey)}
                  >
                    {tierKey === "ALL"
                      ? "All"
                      : tierKey === "REVIEW"
                        ? "Needs review"
                        : tierKey.replace("-TIER", "")}{" "}
                    <span className="ml-1 font-mono text-[10px] opacity-60">
                      {tierCounts[tierKey]}
                    </span>
                  </button>
                ))}
              </div>

              <label className="sr-only" htmlFor="clip-sort">
                Sort clips
              </label>
              <div className="w-[176px]">
                <select
                  id="clip-sort"
                  value={clipSort}
                  onChange={(e) =>
                    setClipSort(e.target.value as "tier_desc" | "tier_asc" | "score_desc" | "newest")
                  }
                  className="select h-8 text-[11.5px]"
                >
                  <option value="tier_desc">Tier, S to B</option>
                  <option value="tier_asc">Tier, B to S</option>
                  <option value="score_desc">Score, high to low</option>
                  <option value="newest">Newest first</option>
                </select>
              </div>
            </div>
          </div>

          {clips.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[#222936] px-4 py-14 text-center text-[11.5px] leading-relaxed text-[#79776f]">
              No clips exported yet. When a moment crosses the threshold, the vertical Short appears here.
            </div>
          ) : sortedClips.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[#222936] px-4 py-12 text-center text-[11.5px] text-[#79776f]">
              No {tierFilter.toLowerCase().replace("-tier", "")} clips right now.{" "}
              <button
                type="button"
                onClick={() => setTierFilter("ALL")}
                className="text-[#e5a183] underline underline-offset-2"
              >
                Show all {clips.length}
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
              <div className="max-h-[560px] space-y-1 overflow-y-auto pr-1 lg:col-span-5">
                {sortedClips.map((c) => {
                  const key = `${c.channel}/${c.clip_id}`;
                  const active = selectedClip && `${selectedClip.channel}/${selectedClip.clip_id}` === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setSelectedClipKey(key)}
                      aria-current={active ? "true" : undefined}
                      className={`relative w-full rounded-xl border px-3.5 py-3 text-left transition-colors ${
                        active
                          ? "border-[#e5a183]/40 bg-[#e5a183]/08"
                          : "border-transparent hover:border-[#222936] hover:bg-white/[0.03]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className={`chip ${latestTierChip(c.tier)}`}>
                            {c.tier} · {c.total_score}
                          </span>
                          {c.needs_human_review && !c.human_review && (
                            <span className="chip chip-neutral" title="A or S tier review is queued">
                              Review pending
                            </span>
                          )}
                          {c.human_review && (
                            <span
                              className={`chip ${
                                c.human_review.verdict === "POST"
                                  ? "chip-ok"
                                  : c.human_review.verdict === "MAYBE"
                                    ? "chip-warn"
                                    : "chip-danger"
                              }`}
                            >
                              {c.human_review.verdict} {c.human_review.human_score}
                            </span>
                          )}
                        </div>
                        <span className="shrink-0 font-mono text-[10px] text-[#79776f]">{c.size_mb} MB</span>
                      </div>
                      <p className="mt-1.5 truncate text-[12.5px] font-medium text-[#ecebe6]">
                        {c.archetype} · @{c.channel}
                      </p>
                      <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-[#79776f]">
                        {c.transcript || c.clip_id}
                      </p>
                      <div className="mt-1.5 flex items-center justify-between font-mono text-[10px] text-[#79776f]">
                        <span className="truncate">{c.clip_id}</span>
                        <span className={c.human_approved ? "text-[#9ed6b8]" : "text-[#dbb675]"}>
                          {c.human_approved ? "Approved" : "Checklist open"}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>

              {selectedClip && (
                <div className="grid grid-cols-1 gap-4 rounded-xl border border-[#1a1f28] bg-[#0b0e13] p-4 sm:grid-cols-12 lg:col-span-7">
                  <div className="flex flex-col items-center sm:col-span-5">
                    <video
                      key={`${selectedClip.video_url}-${selectedClip.mtime}`}
                      src={`${selectedClip.video_url}?v=${Math.floor(selectedClip.mtime)}`}
                      controls
                      playsInline
                      className="aspect-[9/16] w-full max-w-[270px] rounded-xl border border-[#222936] bg-black object-contain"
                    />
                  </div>

                  <div className="flex flex-col justify-between gap-3 sm:col-span-7">
                    <div className="space-y-2.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`chip ${latestTierChip(selectedClip.tier)}`}>
                          {selectedClip.tier} · {selectedClip.total_score}/100
                        </span>
                        <span className="font-mono text-[10.5px] text-[#79776f]">
                          Lookback {selectedClip.pre_pad_used}s · post {selectedClip.post_pad_used}s
                        </span>
                      </div>

                      <div>
                        <p className="text-[13.5px] font-medium text-white">{selectedClip.archetype}</p>
                        <p className="mt-0.5 font-mono text-[10.5px] text-[#79776f]">
                          @{selectedClip.channel} · {selectedClip.clip_id}.mp4
                        </p>
                      </div>

                      <div className="panel-inset p-3">
                        <p className="label mb-1">Transcript</p>
                        <p className="text-[11.5px] leading-relaxed text-[#a3a099]">
                          {selectedClip.transcript || "No transcript"}
                        </p>
                      </div>

                      {selectedClip.human_review && (
                        <div
                          className={`space-y-1.5 rounded-xl border p-3 ${
                            selectedClip.human_review.verdict === "POST"
                              ? "border-[#7fc8a3]/30 bg-[#7fc8a3]/07"
                              : selectedClip.human_review.verdict === "MAYBE"
                                ? "border-[#dbb675]/30 bg-[#dbb675]/07"
                                : "border-[#e08a8a]/30 bg-[#e08a8a]/07"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-[10.5px] font-medium text-[#ecebe6]">
                              Viewer verdict: {selectedClip.human_review.verdict} ·{" "}
                              {selectedClip.human_review.human_score}/100
                            </span>
                            <span className="font-mono text-[9.5px] text-[#79776f]">
                              {selectedClip.human_review.model}
                            </span>
                          </div>
                          <p className="text-[11.5px] italic leading-relaxed text-[#a3a099]">
                            &ldquo;{selectedClip.human_review.gut_reaction}&rdquo;
                          </p>
                          <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[9.5px] text-[#79776f]">
                            <span>Swipe {selectedClip.human_review.swipe_stop}</span>
                            <span>Clarity {selectedClip.human_review.clarity}</span>
                            <span>Fun {selectedClip.human_review.entertainment}</span>
                            <span>Loop {selectedClip.human_review.share_loop}</span>
                          </div>
                          {selectedClip.human_review.edit_tip && (
                            <p className="text-[10.5px] leading-relaxed text-[#79776f]">
                              Tip: {selectedClip.human_review.edit_tip}
                            </p>
                          )}
                        </div>
                      )}

                      {selectedClip.metadata_md && (
                        <details className="panel-inset p-3">
                          <summary className="cursor-pointer font-mono text-[10.5px] text-[#9dbbcf]">
                            Draft metadata and sources
                          </summary>
                          <pre className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-[10.5px] leading-relaxed text-[#79776f]">
                            {selectedClip.metadata_md}
                          </pre>
                        </details>
                      )}
                    </div>

                    <div className="space-y-2.5 border-t border-[#1a1f28] pt-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleToggleApprove(selectedClip)}
                          className={`btn btn-xs ${selectedClip.human_approved ? "btn-secondary" : "btn-primary"}`}
                        >
                          {selectedClip.human_approved ? "Approved · revoke" : "Approve checklist"}
                        </button>
                        <button
                          type="button"
                          disabled={
                            humanReviewingKey === `${selectedClip.channel}/${selectedClip.clip_id}`
                          }
                          onClick={() => handleHumanReview(selectedClip)}
                          className="btn btn-xs btn-secondary"
                        >
                          {humanReviewingKey === `${selectedClip.channel}/${selectedClip.clip_id}`
                            ? "Reviewing"
                            : selectedClip.human_review
                              ? "Review again"
                              : "Human review"}
                        </button>
                        <button
                          type="button"
                          onClick={() => setUploadClip(selectedClip)}
                          className="btn btn-xs btn-secondary"
                        >
                          {selectedClip.youtube_upload ? "Re-upload" : "Upload to YouTube"}
                        </button>
                        {selectedClip.youtube_upload && (
                          <a
                            href={selectedClip.youtube_upload.studio_url}
                            target="_blank"
                            rel="noreferrer"
                            className="btn btn-xs btn-ghost"
                          >
                            YouTube Studio ↗
                          </a>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <a
                          href={selectedClip.video_url}
                          download={`${selectedClip.clip_id}.mp4`}
                          className="btn btn-xs btn-ghost"
                        >
                          Download MP4
                        </a>
                        <button
                          type="button"
                          disabled={deletingKey === `${selectedClip.channel}/${selectedClip.clip_id}`}
                          onClick={() => handleDeleteClip(selectedClip)}
                          onMouseLeave={() => {
                            if (confirmDeleteKey === `${selectedClip.channel}/${selectedClip.clip_id}`) {
                              setConfirmDeleteKey(null);
                            }
                          }}
                          className={`btn btn-xs ${
                            confirmDeleteKey === `${selectedClip.channel}/${selectedClip.clip_id}`
                              ? "btn-danger"
                              : "btn-ghost"
                          }`}
                        >
                          {deletingKey === `${selectedClip.channel}/${selectedClip.clip_id}`
                            ? "Deleting"
                            : confirmDeleteKey === `${selectedClip.channel}/${selectedClip.clip_id}`
                              ? "Confirm delete"
                              : "Delete"}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {uploadClip && (
        <YouTubeUploadModal
          target={uploadClip.clip_id}
          targetType="clip"
          channel={uploadClip.channel}
          onClose={() => setUploadClip(null)}
          onUploaded={pollStatus}
          onOpenConnectTab={onOpenYouTubeTab}
        />
      )}
    </div>
  );
}

function MetricBox({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "ok" | "warn" | "danger" | "accent" | "muted";
}) {
  const color =
    tone === "ok"
      ? "text-[#9ed6b8]"
      : tone === "warn"
        ? "text-[#e6c894]"
        : tone === "danger"
          ? "text-[#e9aaaa]"
          : tone === "accent"
            ? "text-[#e5a183]"
            : "text-[#ecebe6]";
  return (
    <div className="stat bg-[#101319]">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${color}`}>{value}</div>
      <div className="stat-sub truncate">{sub}</div>
    </div>
  );
}

function SignalBar({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between font-mono text-[10.5px]">
        <span className="text-[#a3a099]">{label}</span>
        <span className="text-[#79776f]">
          {value.toFixed(1)} / {max}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[#0b0e13]">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}
