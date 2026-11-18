import React, { useEffect, useState } from "react";
import type {
  YouTubeMetadataPreview,
  YouTubeProfileKey,
  YouTubeStatus,
  YouTubeUploadJob,
} from "@/lib/types";

interface Props {
  target: string;
  targetType: "project" | "clip";
  channel?: string;
  onClose: () => void;
  onUploaded?: () => void;
  onOpenConnectTab?: () => void;
}

const CATEGORIES: Array<[string, string]> = [
  ["20", "Gaming"],
  ["24", "Entertainment"],
  ["28", "Science & Technology"],
  ["22", "People & Blogs"],
  ["27", "Education"],
  ["25", "News & Politics"],
  ["1", "Film & Animation"],
];

export default function YouTubeUploadModal({
  target,
  targetType,
  channel,
  onClose,
  onUploaded,
  onOpenConnectTab,
}: Props) {
  const defaultProfile: YouTubeProfileKey = targetType === "clip" ? "clipper" : "studio";
  const [selectedProfile, setSelectedProfile] = useState<YouTubeProfileKey>(defaultProfile);
  const [ytStatus, setYtStatus] = useState<YouTubeStatus | null>(null);
  const [preview, setPreview] = useState<YouTubeMetadataPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [hashtagsText, setHashtagsText] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [categoryId, setCategoryId] = useState("20");
  const [privacy, setPrivacy] = useState<"private" | "unlisted" | "public">("private");
  const [publishAtLocal, setPublishAtLocal] = useState("");
  const [containsSynthetic, setContainsSynthetic] = useState(true);
  const [approveNow, setApproveNow] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [job, setJob] = useState<YouTubeUploadJob | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setErr(null);
      try {
        const [stRes, prevRes] = await Promise.all([
          fetch("/api/youtube/status"),
          fetch("/api/youtube/preview-metadata", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target, type: targetType, channel }),
          }),
        ]);
        const stData = await stRes.json();
        const prevData = await prevRes.json();
        if (!prevRes.ok) throw new Error(prevData.error || "Failed to generate metadata preview");
        if (cancelled) return;
        setYtStatus(stData);
        setPreview(prevData);
        setSelectedProfile(prevData.default_profile || defaultProfile);
        setTitle(prevData.title || "");
        setDescription(prevData.description || "");
        setHashtagsText((prevData.hashtags || []).join(" "));
        setTagsText((prevData.tags || []).join(", "));
        setCategoryId(prevData.category_id || "20");
        setPrivacy(prevData.privacy_status || "private");
        setContainsSynthetic(Boolean(prevData.contains_synthetic_media));
        setApproveNow(Boolean(prevData.human_approved));
      } catch (e: unknown) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Failed to load preview");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [target, targetType, channel, defaultProfile]);

  useEffect(() => {
    if (!job || job.status !== "UPLOADING") return;
    let missingPolls = 0;
    const id = setInterval(async () => {
      try {
        const res = await fetch("/api/youtube/status");
        if (!res.ok) return;
        const st: YouTubeStatus = await res.json();
        const fresh = (st.active_uploads || []).find((u) => u.job_id === job.job_id);
        if (fresh) {
          missingPolls = 0;
          setJob(fresh);
          if (fresh.status === "DONE") {
            onUploaded?.();
          }
        } else {
          missingPolls += 1;
          if (missingPolls >= 3) {
            setJob((prev) =>
              prev
                ? {
                    ...prev,
                    status: "ERROR",
                    error:
                      "Upload was interrupted (the Studio API restarted mid-upload). Close this modal and click Upload again — nothing was double-published.",
                  }
                : prev
            );
          }
        }
      } catch {
        // ignore transient poll error
      }
    }, 1000);
    return () => clearInterval(id);
  }, [job, onUploaded]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      const publishAtIso = publishAtLocal ? new Date(publishAtLocal).toISOString() : undefined;
      const res = await fetch("/api/youtube/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target,
          type: targetType,
          channel,
          profile: selectedProfile,
          title,
          description,
          hashtags: hashtagsText,
          tags: tagsText,
          category_id: categoryId,
          privacy_status: publishAtIso ? "private" : privacy,
          publish_at: publishAtIso,
          contains_synthetic_media: containsSynthetic,
          approve_now: approveNow,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Upload failed");
      setJob(json.job);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  const parsedTags = tagsText
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  const tagCharCount = parsedTags.reduce((acc, t) => acc + t.length + (t.includes(" ") ? 3 : 1), 0);

  const selectedSlot = ytStatus?.profiles?.[selectedProfile];
  const selectedConnected = Boolean(selectedSlot?.connected && selectedSlot.channel);

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="w-full max-w-2xl bg-[#12151B] border border-[#343C4A] rounded-2xl shadow-2xl overflow-hidden my-6">
        <div className="px-6 py-4 bg-[#0D1015] border-b border-[#232934] flex items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-rose-500" />
              Upload to YouTube
              {preview?.is_short && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#E3A484]/20 text-[#E3A484] border border-[#E3A484]/40">
                  SHORTS 9:16
                </span>
              )}
            </h3>
            <p className="text-xs text-slate-400 font-mono mt-0.5">
              {preview
                ? `${preview.video_size_mb} MB · ${preview.video_info.duration}s · ${preview.video_info.width}×${preview.video_info.height}`
                : target}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg bg-[#181C23] text-xs font-mono text-slate-300 hover:text-white cursor-pointer"
          >
            Close
          </button>
        </div>

        <div className="p-6 max-h-[80vh] overflow-y-auto space-y-4">
          {loading ? (
            <div className="py-12 text-center text-xs font-mono text-slate-400">
              Generating SEO title, hashtags, tags &amp; checking YouTube channels...
            </div>
          ) : (
            <>
              {/* Strict Channel Routing Lock: Clips -> ClipSurge only, Studio Videos -> Paper Trail only */}
              {selectedConnected && selectedSlot?.channel && (
                <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/35 px-4 py-3 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-3">
                    {selectedSlot.channel.thumbnail_url && (
                      <img
                        src={selectedSlot.channel.thumbnail_url}
                        alt={selectedSlot.channel.title}
                        className="w-8 h-8 rounded-full border border-emerald-400/50"
                      />
                    )}
                    <div>
                      <div className="text-[10px] font-medium uppercase tracking-wider text-emerald-300/90">
                        {selectedProfile === "clipper"
                          ? "🔒 Locked to Live Clipper Channel (Clips Only)"
                          : "🔒 Locked to Main Studio Channel (Studio Videos Only)"}
                      </div>
                      <div className="text-sm font-bold text-white">
                        {selectedSlot.channel.title}{" "}
                        {selectedSlot.channel.custom_url && (
                          <span className="text-xs font-mono font-normal text-slate-300">
                            ({selectedSlot.channel.custom_url})
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <span className="px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/35 font-mono text-[10px] font-bold text-emerald-300">
                    ✓ OAuth Ready
                  </span>
                </div>
              )}

              {!selectedConnected && (
                <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-4 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div>
                    <strong className="text-amber-300">
                      {selectedProfile === "clipper"
                        ? "Live Clipper Channel (ClipSurge) not connected yet."
                        : "Main Studio Channel (Paper Trail) not connected yet."}
                    </strong>
                    <p className="text-slate-300 mt-0.5">
                      {selectedProfile === "clipper"
                        ? "Live clips can ONLY upload to the dedicated Live Clipper channel (never Paper Trail)."
                        : "Studio videos can ONLY upload to the Main Studio channel (never ClipSurge)."}
                    </p>
                  </div>
                  {onOpenConnectTab && (
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        onOpenConnectTab();
                      }}
                      className="px-3.5 py-2 rounded-lg bg-[#E3A484] text-slate-950 font-bold cursor-pointer"
                    >
                      Connect Channel
                    </button>
                  )}
                </div>
              )}

              {job ? (
                <div className="rounded-2xl bg-[#0A0C10] border border-[#232934] p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-white">
                      {job.status === "UPLOADING"
                        ? "Uploading video to YouTube..."
                        : job.status === "DONE"
                          ? "✅ Upload Complete!"
                          : "Upload Failed"}
                    </span>
                    <span className="font-mono text-xs text-[#E3A484] font-bold">{job.progress}%</span>
                  </div>

                  <div className="h-3 rounded-full panel overflow-hidden">
                    <div
                      className={`h-full transition-all duration-300 ${
                        job.status === "ERROR"
                          ? "bg-rose-500"
                          : job.status === "DONE"
                            ? "bg-emerald-400"
                            : "bg-[#E3A484]"
                      }`}
                      style={{ width: `${job.progress}%` }}
                    />
                  </div>

                  {job.error && (
                    <div className="rounded-xl bg-rose-500/15 border border-rose-500/40 p-3 text-xs text-rose-200 font-mono">
                      {job.error}
                    </div>
                  )}

                  {job.receipt && (
                    <div className="space-y-3 pt-2">
                      <div className="text-xs text-slate-300">
                        <div>
                          <span className="text-slate-500">Channel:</span>{" "}
                          <strong className="text-emerald-300">{job.receipt.channel_title}</strong>
                        </div>
                        <div className="mt-1">
                          <span className="text-slate-500">Title:</span> {job.receipt.title}
                        </div>
                        <div className="mt-1">
                          <span className="text-slate-500">Visibility:</span>{" "}
                          <span className="uppercase font-mono text-amber-300">
                            {job.receipt.privacy_status}
                          </span>
                        </div>
                        {job.receipt.local_clip_deleted && (
                          <div className="mt-1.5 text-[11px] font-mono text-emerald-300">
                            ✓ Local clip deleted from disk (freed {job.receipt.freed_mb ?? 0} MB) · receipt saved to upload history
                          </div>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <a
                          href={job.receipt.studio_url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-4 py-2 rounded-xl bg-[#E3A484] text-slate-950 text-xs font-bold"
                        >
                          Open in YouTube Studio ↗
                        </a>
                        <a
                          href={job.receipt.url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-4 py-2 rounded-xl bg-[#181C23] border border-[#343C4A] text-xs font-semibold text-sky-300"
                        >
                          Watch Link ↗
                        </a>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <form onSubmit={handleUpload} className="space-y-4">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[11px] font-mono uppercase text-slate-400">
                        Video Title
                      </label>
                      <span
                        className={`text-[11px] font-mono ${
                          title.length > 100 ? "text-rose-400" : "text-slate-400"
                        }`}
                      >
                        {title.length}/100
                      </span>
                    </div>
                    <input
                      type="text"
                      required
                      maxLength={100}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3 py-2 text-sm text-white focus:outline-none focus:border-[#E3A484]"
                    />
                    {preview?.title_options && preview.title_options.length > 1 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {preview.title_options.map((opt, idx) => {
                          const active = title.trim() === opt.trim();
                          return (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => setTitle(opt)}
                              className={`text-[11px] px-2.5 py-1 rounded-lg border transition-colors text-left cursor-pointer ${
                                active
                                  ? "bg-[#E3A484]/20 border-[#E3A484]/60 text-[#F6CDB8]"
                                  : "bg-[#0D1015] border-[#343C4A] text-slate-300 hover:border-slate-500 hover:text-white"
                              }`}
                            >
                              {idx + 1}. {opt}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-[11px] font-mono uppercase text-slate-400 mb-1">
                      Hashtags (auto-appended cleanly to description · sweet spot 3–6)
                    </label>
                    <input
                      type="text"
                      value={hashtagsText}
                      onChange={(e) => setHashtagsText(e.target.value)}
                      placeholder="#Shorts #GTAVI #GTA6 #Gaming #CreatorRadar"
                      className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3 py-2 text-xs font-mono text-sky-300 focus:outline-none focus:border-[#8FB0CE]"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-mono uppercase text-slate-400 mb-1">
                      Description (includes Chapters, Sources &amp; Rule 5 AI Disclosure)
                    </label>
                    <textarea
                      rows={6}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3 py-2 text-xs text-slate-200 font-mono focus:outline-none focus:border-[#8FB0CE]"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[11px] font-mono uppercase text-slate-400">
                        YouTube Search Tags (comma-separated)
                      </label>
                      <span
                        className={`text-[11px] font-mono ${
                          tagCharCount > 480 ? "text-amber-400" : "text-slate-400"
                        }`}
                      >
                        {parsedTags.length} tags · {tagCharCount}/500 chars
                      </span>
                    </div>
                    <input
                      type="text"
                      value={tagsText}
                      onChange={(e) => setTagsText(e.target.value)}
                      className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-[#8FB0CE]"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-[11px] font-mono uppercase text-slate-400 mb-1">
                        Visibility
                      </label>
                      <select
                        value={privacy}
                        disabled={Boolean(publishAtLocal)}
                        onChange={(e) =>
                          setPrivacy(e.target.value as "private" | "unlisted" | "public")
                        }
                        className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3 py-2 text-xs text-slate-100 disabled:opacity-50"
                      >
                        <option value="private">Private (Studio Draft)</option>
                        <option value="unlisted">Unlisted (Review Link)</option>
                        <option value="public">Public (Go Live Now)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-[11px] font-mono uppercase text-slate-400 mb-1">
                        Category
                      </label>
                      <select
                        value={categoryId}
                        onChange={(e) => setCategoryId(e.target.value)}
                        className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3 py-2 text-xs text-slate-100"
                      >
                        {CATEGORIES.map(([id, label]) => (
                          <option key={id} value={id}>
                            {label} ({id})
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-[11px] font-mono uppercase text-slate-400 mb-1">
                        Schedule Publish (Optional)
                      </label>
                      <input
                        type="datetime-local"
                        value={publishAtLocal}
                        onChange={(e) => setPublishAtLocal(e.target.value)}
                        className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-2.5 py-2 text-xs text-slate-100 font-mono"
                      />
                    </div>
                  </div>

                  <div className="rounded-xl bg-[#0A0C10] border border-[#232934] p-3.5 space-y-2 text-xs">
                    <label className="flex items-center gap-2.5 cursor-pointer text-slate-200">
                      <input
                        type="checkbox"
                        checked={approveNow}
                        onChange={(e) => setApproveNow(e.target.checked)}
                        className="accent-[#E3A484]"
                      />
                      <span>
                        <strong>Rule 4 Owner Sign-Off:</strong> I have reviewed this video, rights
                        clearance, and metadata and approve uploading to{" "}
                        <strong>{selectedSlot?.channel?.title || selectedProfile}</strong>.
                      </span>
                    </label>
                    <label className="flex items-center gap-2.5 cursor-pointer text-slate-400">
                      <input
                        type="checkbox"
                        checked={containsSynthetic}
                        onChange={(e) => setContainsSynthetic(e.target.checked)}
                        className="accent-[#8FB0CE]"
                      />
                      <span>
                        Declare altered / synthetic AI media flag (YouTube altered-content policy)
                      </span>
                    </label>
                  </div>

                  {err && (
                    <div className="rounded-xl bg-rose-500/15 border border-rose-500/40 px-3.5 py-2.5 text-xs text-rose-200">
                      {err}
                    </div>
                  )}

                  <div className="flex items-center justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={onClose}
                      className="px-4 py-2 rounded-xl bg-[#181C23] text-xs font-semibold text-slate-300 hover:text-white cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={submitting || !selectedConnected || !approveNow}
                      className="px-5 py-2.5 rounded-xl bg-[#E3A484] text-slate-950 text-xs font-bold hover:brightness-110 disabled:opacity-40 cursor-pointer"
                    >
                      {submitting
                        ? "Starting Upload..."
                        : publishAtLocal
                          ? "Schedule Upload to YouTube"
                          : `Upload to ${selectedSlot?.channel?.title || selectedProfile} (${privacy.toUpperCase()})`}
                    </button>
                  </div>
                </form>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
