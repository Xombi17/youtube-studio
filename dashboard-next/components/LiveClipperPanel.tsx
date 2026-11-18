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

function tierBadgeClass(tier: string) {
  if (tier === "S-TIER") return "bg-amber-400/20 text-amber-300 border-amber-400/40";
  if (tier === "A-TIER") return "bg-[#E3A484]/20 text-[#E3A484] border-[#E3A484]/40";
  return "bg-sky-500/15 text-sky-300 border-sky-500/30";
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

  return (
    <div className="space-y-6">
      {/* Live Stream Scout & Parallel Auto-Clipper */}
      <section className="panel p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Live Stream Scout &amp; Parallel Auto-Clipper
              {data?.auto_scout?.enabled && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                  AUTO-SCOUT ON ({data.auto_scout.max_parallel}×)
                </span>
              )}
            </h2>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Finds the hottest live Twitch &amp; YouTube streams right now and launches parallel 0-VRAM clipping sessions automatically.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={scoutGame}
              onChange={(e) => {
                setScoutGame(e.target.value);
                handleDiscoverStreams(e.target.value, scoutLang);
              }}
              className="rounded-lg bg-[#0A0C10] border border-[#2A313D] px-2.5 py-1.5 text-xs font-mono text-slate-200"
            >
              <option value="Grand Theft Auto VI">GTA VI (GTA 6)</option>
              <option value="ALL">Top All Games</option>
              <option value="Just Chatting">Just Chatting</option>
              <option value="Grand Theft Auto V">GTA V</option>
              <option value="VALORANT">VALORANT</option>
              <option value="Minecraft">Minecraft</option>
              <option value="Fortnite">Fortnite</option>
            </select>

            <select
              value={scoutLang}
              onChange={(e) => {
                setScoutLang(e.target.value);
                handleDiscoverStreams(scoutGame, e.target.value);
              }}
              className="rounded-lg bg-[#0A0C10] border border-[#2A313D] px-2.5 py-1.5 text-xs font-mono text-slate-200"
            >
              <option value="EN">English</option>
              <option value="ALL">All Languages</option>
            </select>

            <select
              value={scoutMaxParallel}
              onChange={(e) => setScoutMaxParallel(Number(e.target.value))}
              className="rounded-lg bg-[#0A0C10] border border-[#2A313D] px-2.5 py-1.5 text-xs font-mono text-slate-200"
              title="Max simultaneous parallel streams"
            >
              <option value={2}>2× Parallel</option>
              <option value={3}>3× Parallel</option>
              <option value={4}>4× Parallel</option>
            </select>

            <button
              type="button"
              disabled={scoutLoading}
              onClick={() => handleDiscoverStreams()}
              className="px-3 py-1.5 rounded-lg bg-[#181C23] border border-[#343C4A] text-xs font-mono text-slate-200 hover:text-white cursor-pointer disabled:opacity-50"
            >
              {scoutLoading ? "Scanning..." : "Scan Live"}
            </button>

            <button
              type="button"
              disabled={scoutBusy}
              onClick={handleAutoClipTopN}
              className="px-3.5 py-1.5 rounded-lg bg-[#E3A484] text-slate-950 text-xs font-bold hover:bg-[#F0B79A] cursor-pointer disabled:opacity-50"
            >
              ⚡ Auto-Clip Top {scoutMaxParallel}
            </button>

            <button
              type="button"
              disabled={scoutBusy}
              onClick={handleToggleAutoScout}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold border cursor-pointer transition disabled:opacity-50 ${
                data?.auto_scout?.enabled
                  ? "bg-emerald-500/20 border-emerald-400/60 text-emerald-300"
                  : "bg-[#0A0C10] border-[#2A313D] text-slate-300 hover:border-emerald-500/50"
              }`}
            >
              {data?.auto_scout?.enabled ? "● Auto-Scout ON" : "Auto-Scout OFF"}
            </button>
          </div>
        </div>

        {scoutNotice && (
          <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/35 px-3 py-2 text-xs font-mono text-emerald-200">
            {scoutNotice}
          </div>
        )}

        {scoutStreams.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {scoutStreams.slice(0, 8).map((item) => {
              const isLiveClip =
                item.already_clipping ||
                sessions.some(
                  (s) =>
                    s.running &&
                    (s.channel.toLowerCase() === item.suggested_channel.toLowerCase() ||
                      (s.state.url || "").toLowerCase().replace(/\/$/, "") === item.url.toLowerCase().replace(/\/$/, ""))
                );
              return (
                <div
                  key={item.id}
                  className={`rounded-xl bg-[#0A0C10] border overflow-hidden flex flex-col justify-between transition ${
                    isLiveClip ? "border-emerald-500/60" : "border-[#1E232C] hover:border-[#3C4553]"
                  }`}
                >
                  <div>
                    <div className="relative aspect-video bg-black">
                      {item.thumbnail_url && (
                        <img
                          src={item.thumbnail_url}
                          alt={item.display_name}
                          className="w-full h-full object-cover"
                        />
                      )}
                      <div className="absolute top-1.5 left-1.5 flex items-center gap-1">
                        <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-rose-600/90 text-white">
                          LIVE {item.viewers > 0 ? `· ${(item.viewers / 1000).toFixed(1)}K` : ""}
                        </span>
                        {item.is_watchlist && (
                          <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-amber-500/90 text-slate-950">
                            ★
                          </span>
                        )}
                      </div>
                      <span className="absolute bottom-1.5 right-1.5 text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-black/75 text-slate-200">
                        {item.platform} · {item.language}
                      </span>
                    </div>
                    <div className="p-2.5">
                      <div className="text-xs font-bold text-white truncate">{item.display_name}</div>
                      <div className="text-[11px] text-slate-400 line-clamp-1 mt-0.5" title={item.title}>
                        {item.title || item.game}
                      </div>
                    </div>
                  </div>
                  <div className="px-2.5 pb-2.5 flex items-center justify-between gap-2">
                    <span className="text-[10px] font-mono text-slate-500 truncate">{item.game}</span>
                    {isLiveClip ? (
                      <span className="text-[10px] font-mono font-bold px-2 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                        ● CLIPPING
                      </span>
                    ) : (
                      <button
                        type="button"
                        disabled={scoutBusy}
                        onClick={() => handleClipDiscovered(item)}
                        className="text-[10px] font-mono font-bold px-2.5 py-1 rounded-lg bg-[#191E26] hover:bg-[#E3A484] hover:text-slate-950 text-sky-300 border border-[#343C4A] cursor-pointer transition disabled:opacity-50"
                      >
                        + Clip Live
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Multi-Stream Active Sessions Bar */}
      {sessions.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 panel px-4 py-3">
          <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400 mr-1">
            Streams ({runningCount} live):
          </span>
          {sessions.map((s) => {
            const isSel = activeSession?.channel === s.channel;
            return (
              <div
                key={s.channel}
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-mono transition ${
                  isSel
                    ? "bg-[#1B2029] border-[#E3A484] text-white"
                    : "bg-[#0A0C10] border-[#343C4A] text-slate-300 hover:border-[#3C4553]"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setSelectedSession(s.channel)}
                  className="inline-flex items-center gap-2 cursor-pointer"
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      s.running ? "bg-rose-500 animate-pulse" : "bg-slate-600"
                    }`}
                  />
                  <span>@{s.channel}</span>
                  <span className="text-[10px] text-slate-400">
                    ({s.state.segments_scanned} segs)
                  </span>
                </button>
                {s.running && (
                  <button
                    type="button"
                    title={`Stop @${s.channel}`}
                    onClick={() => handleStop(s.channel)}
                    className="ml-1 text-[10px] text-rose-400 hover:text-rose-200 cursor-pointer"
                  >
                    ✕
                  </button>
                )}
              </div>
            );
          })}
          {runningCount > 1 && (
            <button
              type="button"
              onClick={() => handleStop()}
              className="ml-auto px-2.5 py-1 rounded-lg bg-rose-500/15 border border-rose-500/30 text-[11px] font-mono text-rose-300 hover:bg-rose-500/25 cursor-pointer"
            >
              Stop All
            </button>
          )}
        </div>
      )}

      {/* Top Launch & Config Bar */}
      <section className="panel p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  running ? "bg-rose-500 animate-pulse shadow-[0_0_12px_rgba(244,63,94,0.8)]" : "bg-slate-600"
                }`}
              />
              <h2 className="text-lg font-semibold text-white">
                Live Stream Auto-Clipper <span className="text-[#E3A484]">v2</span>
              </h2>
              <span className="text-[11px] font-mono px-2.5 py-0.5 rounded-full bg-[#0A0C10] border border-[#2A313D] text-slate-300">
                {running ? st?.status || "LISTENING LIVE" : "IDLE"}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Multi-stream concurrent clipper · Paste another URL with a new Channel Label to clip multiple streams simultaneously!
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={busy || !url.trim()}
              onClick={handleStart}
              className="px-4 py-2 rounded-xl bg-[#E3A484] hover:bg-[#F0B79A] text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-50"
            >
              {busy ? "Connecting..." : runningCount > 0 ? "+ Add / Restart Stream" : "Start Live Clipper"}
            </button>
            {running && activeSession && (
              <button
                type="button"
                disabled={busy}
                onClick={() => handleStop(activeSession.channel)}
                className="px-4 py-2 rounded-xl bg-rose-500/20 border border-rose-500/50 text-rose-200 hover:bg-rose-500/30 text-xs font-bold cursor-pointer disabled:opacity-50"
              >
                {busy ? "Stopping..." : `Stop @${activeSession.channel}`}
              </button>
            )}
          </div>
        </div>

        <form onSubmit={handleStart} className="grid grid-cols-1 md:grid-cols-12 gap-3">
          <div className="md:col-span-5">
            <label className="block text-[10px] font-medium uppercase text-slate-400 mb-1">
              Twitch or YouTube Live URL
            </label>
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=... or https://www.twitch.tv/..."
              className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-[#E3A484]"
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-[10px] font-medium uppercase text-slate-400 mb-1">Channel Label</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="mythpat-gta6"
              className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3 py-2 text-xs text-slate-100 font-mono"
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-[10px] font-medium uppercase text-slate-400 mb-1">
              Threshold ({threshold}/100)
            </label>
            <input
              type="range"
              min={72}
              max={85}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full accent-[#E3A484] mt-2"
            />
            <p className="text-[10px] font-mono text-slate-500 mt-1">
              Minimum 72 — the A-tier export gate. Lower scores are never rendered.
            </p>
          </div>

          <div className="md:col-span-1">
            <label className="block text-[10px] font-medium uppercase text-slate-400 mb-1">Max (s)</label>
            <input
              type="number"
              min={15}
              max={60}
              value={maxClipSec}
              onChange={(e) => setMaxClipSec(Number(e.target.value))}
              className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-2.5 py-2 text-xs text-slate-100 font-mono"
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-[10px] font-medium uppercase text-slate-400 mb-1">Output Framing</label>
            <select
              value={layout}
              onChange={(e) => setLayout(e.target.value as "facecam-split" | "pip-overlay" | "split-blur" | "crop" | "landscape")}
              className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-2.5 py-2 text-xs text-slate-100"
            >
              <option value="split-blur">9:16 Split-Blur (Recommended)</option>
              <option value="facecam-split">9:16 Zero-Gap Facecam + Game</option>
              <option value="pip-overlay">9:16 Full-Screen Game + Floating Facecam</option>
              <option value="crop">9:16 Center Crop</option>
              <option value="landscape">16:9 Landscape</option>
            </select>
          </div>

          <div className="md:col-span-3">
            <label className="block text-[10px] font-medium uppercase text-slate-400 mb-1">Facecam Corner</label>
            <select
              value={facecamPos}
              disabled={layout !== "facecam-split" && layout !== "pip-overlay"}
              onChange={(e) =>
                setFacecamPos(e.target.value as "top-right" | "top-left" | "bottom-right" | "bottom-left")
              }
              className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-2.5 py-2 text-xs text-slate-100 disabled:opacity-40"
            >
              <option value="top-right">Top-Right (Mythpat / Most YT)</option>
              <option value="top-left">Top-Left</option>
              <option value="bottom-right">Bottom-Right</option>
              <option value="bottom-left">Bottom-Left</option>
            </select>
          </div>

          <div className="md:col-span-3">
            <label className="block text-[10px] font-medium uppercase text-slate-400 mb-1">Speech AI Engine</label>
            <select
              value={asr}
              onChange={(e) => setAsr(e.target.value as "modal" | "hinglish" | "whisper" | "whistle")}
              className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-2.5 py-2 text-xs text-slate-100"
            >
              <option value="modal">Modal Cloud GPU (Free T4 — 0% Laptop GPU)</option>
              <option value="hinglish">Local Whisper Hinglish-Apex (RTX 4060)</option>
              <option value="whisper">Local Whisper Small (RTX 4060)</option>
              <option value="whistle">Local Cactus Whistle (16.9MB EN CPU)</option>
            </select>
          </div>

          <div className="md:col-span-2">
            <label className="block text-[10px] font-medium uppercase text-slate-400 mb-1">Language</label>
            <select
              value={asrLang}
              onChange={(e) => setAsrLang(e.target.value as "auto" | "hi" | "en")}
              className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-2.5 py-2 text-xs text-slate-100"
            >
              <option value="auto">Auto (Hinglish)</option>
              <option value="hi">Force Hindi</option>
              <option value="en">Force English</option>
            </select>
          </div>

          <div className="md:col-span-4">
            <label className="block text-[10px] font-medium uppercase text-slate-400 mb-1">
              Extra Keywords (+ 160 phrases in config)
            </label>
            <input
              type="text"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3 py-2 text-xs text-slate-200 font-mono"
            />
          </div>

          <div className="md:col-span-12 flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-[#1A1F27]">
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoUpload}
                  onChange={(e) => setAutoUpload(e.target.checked)}
                  className="accent-[#E3A484]"
                />
                <span>
                  <strong>Auto-Upload S-Tier Clips (≥ 90) to Clipper Channel</strong>{" "}
                  <span className="text-slate-400">
                    (Private Studio Draft by default · auto-deletes local clip after upload)
                  </span>
                </span>
              </label>

              {clipperYt?.connected && clipperYt.channel ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/35 text-[11px] font-mono text-emerald-300">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  Clipper YT: <strong>{clipperYt.channel.title}</strong>
                  {clipperYt.channel.custom_url ? ` (${clipperYt.channel.custom_url})` : ""}
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => onOpenYouTubeTab?.()}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/15 border border-amber-500/40 text-[11px] font-mono text-amber-300 hover:bg-amber-500/25 cursor-pointer"
                >
                  ⚠ Clipper Channel Not Connected — Connect Now ↗
                </button>
              )}
            </div>
            {autoUpload && (
              <div className="flex items-center gap-2 text-xs">
                <span className="font-mono text-[11px] text-slate-400">Visibility:</span>
                <select
                  value={uploadPrivacy}
                  onChange={(e) => setUploadPrivacy(e.target.value as "private" | "unlisted" | "public")}
                  className="rounded-lg bg-[#0A0C10] border border-[#2A313D] px-2.5 py-1 text-xs text-slate-100"
                >
                  <option value="private">Private (YouTube Studio Draft — Safe)</option>
                  <option value="unlisted">Unlisted</option>
                  <option value="public">Public (Go Live Immediately)</option>
                </select>
              </div>
            )}
          </div>
        </form>

        {err && (
          <div className="rounded-xl bg-rose-500/15 border border-rose-500/40 px-3 py-2 text-xs text-rose-200">
            {err}
          </div>
        )}
      </section>

      {/* Live Clipper Progress KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <MetricBox
          label="Live Status"
          value={running ? "LIVE" : "IDLE"}
          sub={st?.channel ? `@${st.channel}` : "Paste URL to start"}
          accent={running ? "text-rose-400" : "text-slate-400"}
        />
        <MetricBox
          label="Segments Scanned"
          value={`${st?.segments_scanned ?? 0}`}
          sub={`${((st?.segments_scanned ?? 0) * 10 / 60).toFixed(1)} min analyzed`}
          accent="text-sky-400"
        />
        <MetricBox
          label="Clips In Progress"
          value={`${inProgress.length}`}
          sub={inProgress.length ? inProgress[0].stage.replace("_", " ") : "Waiting for spike"}
          accent={inProgress.length > 0 ? "text-amber-400" : "text-slate-200"}
        />
        <MetricBox
          label="Clips Created"
          value={`${clips.length}`}
          sub={`${clips.filter((c) => c.human_approved).length} human-approved`}
          accent="text-emerald-400"
        />
        <MetricBox
          label="Live Chat Velocity"
          value={latest?.chat?.ratio ? `${latest.chat.ratio.toFixed(1)}x` : "—"}
          sub={
            latest?.chat?.msgs_in_window !== undefined
              ? `${latest.chat.msgs_in_window} msgs / 10s (${latest.chat.unique_authors ?? 0} users)`
              : "Chat monitor standby"
          }
          accent={latest?.chat?.is_explosion ? "text-[#E3A484]" : "text-slate-100"}
        />
      </div>

      {/* Main Split: Embedded Live Stream Player + Live Multimodal Radar & Queue */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left: Embedded Stream Preview */}
        <section className="lg:col-span-7 panel overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-[#232934] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
                Live Stream Monitor
              </span>
              {embed.platform && (
                <span className="text-[10px] font-medium uppercase px-2 py-0.5 rounded bg-[#0A0C10] text-[#E3A484] border border-[#2A313D]">
                  {embed.platform}
                </span>
              )}
            </div>
            {activeUrl && (
              <a
                href={activeUrl}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] font-mono text-sky-400 hover:underline"
              >
                Open Original ↗
              </a>
            )}
          </div>

          <div className="aspect-video bg-black relative">
            {embed.embedUrl ? (
              <iframe
                src={embed.embedUrl}
                title="Live Stream Player"
                className="w-full h-full border-0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-xs text-slate-500 font-mono p-6 text-center">
                Paste a live YouTube or Twitch stream URL above to preview the stream right here.
              </div>
            )}
          </div>

          {/* Rolling 36-Segment Virality Timeline Chart */}
          <div className="p-4 border-t border-[#232934] space-y-2">
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
              <span>Live Virality Timeline (last {history.length} × 10s segments)</span>
              <span>Trigger Line: {st?.threshold ?? threshold}/100</span>
            </div>
            <div className="relative h-24 bg-[#0A0C10] rounded-xl border border-[#1B2029] px-2 pt-3 pb-1 flex items-end gap-1 overflow-hidden">
              {/* Threshold horizontal line */}
              <div
                className="absolute left-0 right-0 border-t border-dashed border-[#E3A484]/60 pointer-events-none"
                style={{ bottom: `${Math.min(95, st?.threshold ?? threshold)}%` }}
              />
              {history.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-[11px] font-mono text-slate-500">
                  Waiting for first 10-second segment...
                </div>
              ) : (
                history.map((pt) => (
                  <div
                    key={`${pt.idx}-${pt.time}`}
                    title={`[${pt.time}] seg_${pt.idx} | Score ${pt.total} (Chat ${pt.chat}, Aud ${pt.audio}, Vis ${pt.visual}, Txt ${pt.txt})`}
                    className="flex-1 min-w-[6px] rounded-t transition-all"
                    style={{
                      height: `${Math.max(5, Math.min(100, pt.total))}%`,
                      backgroundColor: pt.triggered
                        ? "#E3A484"
                        : pt.total >= (st?.threshold ?? threshold) * 0.7
                          ? "#D8B173"
                          : "#9BC4D8",
                    }}
                  />
                ))
              )}
            </div>
          </div>
        </section>

        {/* Right: Multimodal Signal Breakdown + In-Progress Queue + Live Feed */}
        <section className="lg:col-span-5 space-y-4 flex flex-col">
          {/* Live Signal Meters */}
          <div className="panel p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
                Multimodal Signal Radar
              </span>
              {latest && (
                <span className={`text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full border ${tierBadgeClass(latest.tier)}`}>
                  {latest.tier} · {latest.total_score}/100
                </span>
              )}
            </div>

            <SignalBar label="Chat Explosion (Twitch / YT)" value={latest?.chat?.score ?? 0} max={55} color="#E3A484" />
            <SignalBar label="Audio Emotion DSP (Scream/Laugh)" value={latest?.audio?.score ?? 0} max={35} color="#D8B173" />
            <SignalBar label="Transcript Hype & Keywords" value={latest?.transcript_score?.score ?? 0} max={40} color="#9BC4D8" />
            <SignalBar label="Visual Action & Scene Cuts (Cool Plays)" value={latest?.visual?.score ?? 0} max={32} color="#B0A6CE" />

            <div className="pt-2 border-t border-[#1A1F27] flex items-center justify-between text-[11px] font-mono">
              <span className="text-slate-400">Cross-Modal Synergy</span>
              <span
                className={
                  (latest?.synergy ?? 0) > 0
                    ? "text-emerald-400 font-bold"
                    : (latest?.synergy ?? 0) < 0
                      ? "text-rose-400 font-bold"
                      : "text-slate-400"
                }
              >
                {(latest?.synergy ?? 0) >= 0 ? `+${latest?.synergy ?? 0}` : latest?.synergy}{" "}
                {latest?.synergy_reasons?.length ? `(${latest.synergy_reasons.join(", ")})` : ""}
              </span>
            </div>

            {latest?.transcript && (
              <div className="rounded-xl bg-[#0A0C10] border border-[#1B2029] p-2.5 text-xs text-slate-300 font-mono">
                <span className="text-[10px] text-slate-500 block mb-0.5">
                  LATEST SEGMENT [{latest.time}] · {latest.archetype}
                </span>
                “{latest.transcript}”
              </div>
            )}
          </div>

          {/* Clips Currently In Progress */}
          <div className="panel p-4 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
                In-Progress Clip Queue ({inProgress.length})
              </span>
              <span className="text-[10px] font-mono text-slate-500">Auto-renders via NVENC</span>
            </div>
            {inProgress.length === 0 ? (
              <div className="text-xs text-slate-500 font-mono py-2">
                No clips rendering right now. Trigger threshold is {st?.threshold ?? threshold}/100.
              </div>
            ) : (
              <div className="space-y-2">
                {inProgress.map((job, idx) => (
                  <div
                    key={`${job.trigger_idx}-${idx}`}
                    className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-3 flex items-center justify-between gap-2 text-xs"
                  >
                    <div>
                      <div className="font-bold text-amber-200">
                        {job.stage === "EXPORTING_NVENC" ? "Rendering NVENC 9:16..." : "Collecting Post-Pad Reaction..."}
                      </div>
                      <div className="text-[11px] font-mono text-amber-300/80">
                        {job.archetype} · Score {job.score}/100 · seg_{job.trigger_idx}
                      </div>
                    </div>
                    <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping" />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Live Clipper Console Tail */}
          <div className="bg-[#0D1015] border border-[#232934] rounded-2xl overflow-hidden flex-1 flex flex-col min-h-[150px]">
            <div className="px-3.5 py-2 bg-[#12151B] border-b border-[#232934] flex items-center justify-between">
              <span className="text-[11px] font-mono font-bold uppercase text-slate-300">Live Clipper Feed</span>
              <span className="text-[10px] font-mono text-slate-500">{data?.logs?.length ?? 0} lines</span>
            </div>
            <div className="p-3 h-40 overflow-y-auto font-mono text-[11px] space-y-1 text-slate-300">
              {(data?.logs?.length ? data.logs : ["Start a stream to see live 10s segment scores here..."]).map((line, i) => (
                <div
                  key={i}
                  className={
                    line.includes("EXPORTED") || line.includes("SAVED")
                      ? "text-emerald-400 font-semibold"
                      : line.includes("LIVE MOMENT") || line.includes("CLIP TRIGGERED") || line.includes("ESCALATING")
                        ? "text-amber-300 font-semibold"
                        : line.includes("error") || line.includes("failed")
                          ? "text-rose-400"
                          : "text-slate-300"
                  }
                >
                  {line}
                </div>
              ))}
              <div ref={logRef} />
            </div>
          </div>
        </section>
      </div>

      {/* Created Clips Gallery + Built-In Vertical Video Reviewer */}
      <section className="panel p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-base font-bold text-white flex flex-wrap items-center gap-2">
              Created Viral Clips ({clips.length})
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#E3A484]/15 text-[#F6CDB8] border border-[#E3A484]/40">
                S-TIER ≥ 90
              </span>
              {data?.groq_usage?.configured && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/35">
                  Groq Free-Tier: {data.groq_usage.llm_calls_today + data.groq_usage.whisper_calls_today}/{data.groq_usage.rpd_soft_cap} today · {data.groq_usage.calls_saved} saved
                </span>
              )}
            </h3>
            <p className="text-xs text-slate-400">
              Saved under <code>exports/live-clips/</code> with Groq Whisper + Wispr-Flow captions &amp; Blueprint v2 scoring.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={batchReviewing}
              onClick={handleBatchReview}
              className="px-3 py-1.5 rounded-lg bg-[#191E26] border border-[#343C4A] text-xs font-mono font-bold text-sky-300 hover:bg-[#E3A484] hover:text-slate-950 cursor-pointer disabled:opacity-50"
              title="Score & generate cached YouTube titles for up to 3 unreviewed clips in a single Groq API call"
            >
              {batchReviewing ? "Batching..." : "⚡ Batch-Review 3 (1 Groq Call)"}
            </button>
            <button
              type="button"
              disabled={humanReviewingKey === "__s_tier__"}
              onClick={() => handleHumanReview()}
              className="px-3 py-1.5 rounded-lg bg-purple-500/15 border border-purple-400/45 text-xs font-mono font-bold text-purple-200 hover:bg-purple-500/30 cursor-pointer disabled:opacity-50"
              title="Run the simulated normal-human viewer agent (gpt-oss-120b) on unreviewed A-Tier and S-Tier clips"
            >
              {humanReviewingKey === "__s_tier__" ? "Reviewing..." : "🧠 Human-Review A/S"}
            </button>
            {/* Tier Filter Pills */}
            <div className="inline-flex items-center gap-1 rounded-xl bg-[#0A0C10] border border-[#2A313D] p-1">
              {(["ALL", "S-TIER", "A-TIER", "B-TIER", "REVIEW"] as const).map((tierKey) => {
                const isActive = tierFilter === tierKey;
                const count = tierCounts[tierKey];
                return (
                  <button
                    key={tierKey}
                    type="button"
                    onClick={() => setTierFilter(tierKey)}
                    className={`px-2.5 py-1 rounded-lg text-[11px] font-mono font-semibold transition cursor-pointer ${
                      isActive
                        ? tierKey === "S-TIER"
                          ? "bg-[#E3A484]/25 text-[#F6CDB8] border border-[#E3A484]/50"
                          : tierKey === "A-TIER"
                            ? "bg-amber-500/20 text-amber-200 border border-amber-500/45"
                            : tierKey === "B-TIER"
                              ? "bg-sky-500/20 text-sky-200 border border-sky-500/45"
                              : tierKey === "REVIEW"
                                ? "bg-purple-500/25 text-purple-200 border border-purple-400/55"
                                : "bg-[#1B2029] text-white border border-[#3C4553]"
                        : "text-slate-400 hover:text-slate-200 border border-transparent"
                    }`}
                  >
                    {tierKey === "ALL" ? "All" : tierKey === "REVIEW" ? "🧠 Needs review" : tierKey} ({count})
                  </button>
                );
              })}
            </div>

            {/* Tier / Score / Time Sorter */}
            <label className="inline-flex items-center gap-1.5 text-[11px] font-mono text-slate-400">
              <span>Sort:</span>
              <select
                value={clipSort}
                onChange={(e) => setClipSort(e.target.value as "tier_desc" | "tier_asc" | "score_desc" | "newest")}
                className="rounded-lg bg-[#0A0C10] border border-[#2A313D] px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-[#E3A484]"
              >
                <option value="tier_desc">Tier (S → A → B)</option>
                <option value="tier_asc">Tier (B → A → S)</option>
                <option value="score_desc">Score (High → Low)</option>
                <option value="newest">Newest First</option>
              </select>
            </label>

            <button
              type="button"
              onClick={pollStatus}
              className="px-3 py-1.5 rounded-lg bg-[#0A0C10] border border-[#2A313D] text-xs font-mono text-slate-300 hover:text-white cursor-pointer"
            >
              Refresh Clips
            </button>
          </div>
        </div>

        {clips.length === 0 ? (
          <div className="rounded-xl bg-[#0A0C10] border border-[#1B2029] p-8 text-center text-xs font-mono text-slate-500">
            No live clips exported yet. Once a moment crosses threshold, the vertical 9:16 Short will appear here automatically.
          </div>
        ) : sortedClips.length === 0 ? (
          <div className="rounded-xl bg-[#0A0C10] border border-[#1B2029] p-8 text-center text-xs font-mono text-slate-400">
            No {tierFilter} clips right now.{" "}
            <button
              type="button"
              onClick={() => setTierFilter("ALL")}
              className="text-[#E3A484] underline cursor-pointer"
            >
              Show all {clips.length} clips
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Clip List */}
            <div className="lg:col-span-5 space-y-2 max-h-[540px] overflow-y-auto pr-1">
              {sortedClips.map((c) => {
                const key = `${c.channel}/${c.clip_id}`;
                const active = selectedClip && `${selectedClip.channel}/${selectedClip.clip_id}` === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setSelectedClipKey(key)}
                    className={`w-full text-left rounded-xl p-3.5 border transition cursor-pointer ${
                      active
                        ? "bg-[#152238] border-[#E3A484]"
                        : "bg-[#0A0C10] border-[#1E232C] hover:border-[#3C4553]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${tierBadgeClass(c.tier)}`}>
                          {c.tier} · {c.total_score}/100
                        </span>
                        {c.needs_human_review && !c.human_review && (
                          <span
                            className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border bg-purple-500/20 text-purple-200 border-purple-400/45"
                            title="A/S-tier clip — automatic human review is queued or running"
                          >
                            🧠 PENDING REVIEW
                          </span>
                        )}
                        {c.human_review && (
                          <span
                            className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                              c.human_review.verdict === "POST"
                                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/45"
                                : c.human_review.verdict === "MAYBE"
                                  ? "bg-amber-500/20 text-amber-200 border-amber-500/45"
                                  : "bg-rose-500/20 text-rose-300 border-rose-500/45"
                            }`}
                          >
                            🧠 {c.human_review.verdict} {c.human_review.human_score}
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] font-mono text-slate-400">{c.size_mb} MB</span>
                    </div>
                    <div className="text-xs font-bold text-slate-100 mt-1.5 truncate">
                      {c.archetype} · @{c.channel}
                    </div>
                    <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">
                      {c.transcript || c.clip_id}
                    </p>
                    <div className="flex items-center justify-between mt-2 text-[10px] font-mono text-slate-500">
                      <span>{c.clip_id}</span>
                      <span className={c.human_approved ? "text-emerald-400" : "text-amber-400"}>
                        {c.human_approved ? "APPROVED" : "CHECKLIST OPEN"}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Selected Clip Vertical Player & Details */}
            {selectedClip && (
              <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-12 gap-4 bg-[#0A0C10] border border-[#1E232C] rounded-2xl p-4">
                <div className="sm:col-span-5 flex flex-col items-center">
                  <video
                    key={`${selectedClip.video_url}-${selectedClip.mtime}`}
                    src={`${selectedClip.video_url}?v=${Math.floor(selectedClip.mtime)}`}
                    controls
                    playsInline
                    className="w-full max-w-[270px] aspect-[9/16] rounded-xl bg-black border border-[#343C4A] object-contain"
                  />
                </div>
                <div className="sm:col-span-7 space-y-3 flex flex-col justify-between">
                  <div className="space-y-2.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full border ${tierBadgeClass(selectedClip.tier)}`}>
                        {selectedClip.tier} · {selectedClip.total_score}/100
                      </span>
                      <span className="text-[11px] font-mono text-slate-400">
                        Lookback {selectedClip.pre_pad_used}s / Post {selectedClip.post_pad_used}s
                      </span>
                    </div>

                    <div className="text-sm font-bold text-white">{selectedClip.archetype}</div>
                    <div className="text-[11px] font-mono text-slate-400">
                      Channel: @{selectedClip.channel} · File: {selectedClip.clip_id}.mp4
                    </div>

                    <div className="rounded-xl panel p-3 text-xs text-slate-300">
                      <div className="text-[10px] font-medium uppercase text-slate-500 mb-1">Transcript</div>
                      {selectedClip.transcript || "(No transcript)"}
                    </div>

                    {selectedClip.human_review && (
                      <div
                        className={`rounded-xl p-3 border text-xs space-y-1.5 ${
                          selectedClip.human_review.verdict === "POST"
                            ? "bg-emerald-500/10 border-emerald-500/40"
                            : selectedClip.human_review.verdict === "MAYBE"
                              ? "bg-amber-500/10 border-amber-500/40"
                              : "bg-rose-500/10 border-rose-500/40"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono font-bold text-[11px] text-white">
                            🧠 Human Viewer Verdict: {selectedClip.human_review.verdict} ({selectedClip.human_review.human_score}/100)
                          </span>
                          <span className="text-[10px] font-mono text-slate-400">
                            {selectedClip.human_review.model}
                          </span>
                        </div>
                        <p className="text-slate-200 italic">&ldquo;{selectedClip.human_review.gut_reaction}&rdquo;</p>
                        <div className="flex flex-wrap gap-2 text-[10px] font-mono text-slate-300">
                          <span>Swipe: {selectedClip.human_review.swipe_stop}</span>
                          <span>· Clarity: {selectedClip.human_review.clarity}</span>
                          <span>· Fun: {selectedClip.human_review.entertainment}</span>
                          <span>· Loop: {selectedClip.human_review.share_loop}</span>
                        </div>
                        {selectedClip.human_review.edit_tip && (
                          <div className="text-[11px] text-slate-400">
                            Tip: {selectedClip.human_review.edit_tip}
                          </div>
                        )}
                      </div>
                    )}

                    {selectedClip.metadata_md && (
                      <details className="rounded-xl panel p-3 text-xs text-slate-300">
                        <summary className="cursor-pointer font-mono text-[11px] text-sky-400">
                          View Draft Metadata &amp; Sources (metadata.md)
                        </summary>
                        <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px] text-slate-400 max-h-40 overflow-y-auto">
                          {selectedClip.metadata_md}
                        </pre>
                      </details>
                    )}
                  </div>

                  <div className="pt-3 border-t border-[#1A1F27] flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleToggleApprove(selectedClip)}
                        className={`px-3.5 py-2 rounded-xl text-xs font-bold cursor-pointer ${
                          selectedClip.human_approved
                            ? "bg-emerald-500/20 border border-emerald-500/40 text-emerald-300"
                            : "bg-[#E3A484] text-slate-950 hover:bg-[#F0B79A]"
                        }`}
                      >
                        {selectedClip.human_approved ? "✓ Approved (Rule 4 & 5)" : "Approve Clip Checklist (Rule 4)"}
                      </button>
                      <button
                        type="button"
                        disabled={humanReviewingKey === `${selectedClip.channel}/${selectedClip.clip_id}`}
                        onClick={() => handleHumanReview(selectedClip)}
                        className="px-3 py-2 rounded-xl bg-purple-500/15 border border-purple-400/45 text-purple-200 text-xs font-bold hover:bg-purple-500/30 cursor-pointer disabled:opacity-50"
                      >
                        {humanReviewingKey === `${selectedClip.channel}/${selectedClip.clip_id}`
                          ? "Reviewing..."
                          : selectedClip.human_review
                            ? "🧠 Re-Review"
                            : "🧠 Human Review"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setUploadClip(selectedClip)}
                        className="px-3.5 py-2 rounded-xl bg-rose-600 text-white text-xs font-bold hover:bg-rose-500 cursor-pointer"
                      >
                        {selectedClip.youtube_upload ? "Re-Upload to YT" : "Upload to YouTube"}
                      </button>
                      {selectedClip.youtube_upload && (
                        <a
                          href={selectedClip.youtube_upload.studio_url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-3 py-2 rounded-xl bg-rose-500/20 border border-rose-500/40 text-xs font-bold text-rose-200"
                        >
                          YT Studio ↗
                        </a>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <a
                        href={selectedClip.video_url}
                        download={`${selectedClip.clip_id}.mp4`}
                        className="px-3 py-2 rounded-xl bg-[#12151B] border border-[#2A313D] text-xs font-mono text-slate-200 hover:border-slate-400"
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
                        className={`px-3 py-2 rounded-xl text-xs font-bold cursor-pointer transition disabled:opacity-50 ${
                          confirmDeleteKey === `${selectedClip.channel}/${selectedClip.clip_id}`
                            ? "bg-rose-600 text-white border border-rose-400"
                            : "bg-rose-500/10 border border-rose-500/35 text-rose-300 hover:bg-rose-500/20"
                        }`}
                      >
                        {deletingKey === `${selectedClip.channel}/${selectedClip.clip_id}`
                          ? "Deleting..."
                          : confirmDeleteKey === `${selectedClip.channel}/${selectedClip.clip_id}`
                            ? "Confirm Trash?"
                            : "Delete"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
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

function MetricBox({ label, value, sub, accent }: { label: string; value: string; sub: string; accent: string }) {
  return (
    <div className="panel p-4">
      <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`text-2xl font-semibold font-mono mt-1 ${accent}`}>{value}</div>
      <div className="text-[11px] text-slate-500 mt-0.5 truncate">{sub}</div>
    </div>
  );
}

function SignalBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px] font-mono">
        <span className="text-slate-300">{label}</span>
        <span className="text-slate-400">
          {value.toFixed(1)} / {max}
        </span>
      </div>
      <div className="h-2 rounded-full bg-[#0A0C10] border border-[#1B2029] overflow-hidden">
        <div className="h-full rounded-full transition-all duration-300" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}
