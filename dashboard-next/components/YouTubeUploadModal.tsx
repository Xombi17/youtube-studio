import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
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
  const [mounted, setMounted] = useState(false);

  // Prevent background scroll and track client mount for createPortal
  useEffect(() => {
    setMounted(true);
    const origOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = origOverflow;
    };
  }, []);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, submitting]);

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

  if (!mounted) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-3 sm:p-5 bg-black/80 backdrop-blur-md"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) {
          onClose();
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-modal-title"
        className="relative flex flex-col w-full max-w-2xl max-h-[90vh] rounded-2xl border border-[#222936] bg-[#101319] shadow-[0_30px_90px_-20px_rgba(0,0,0,0.9)] overflow-hidden"
      >
        {/* Header - Fixed at top */}
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[#1a1f28] bg-[#0c0f14] px-5 py-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
              <h3 id="upload-modal-title" className="text-[15px] font-semibold tracking-[-0.01em] text-white">
                Upload to YouTube
              </h3>
              {preview?.is_short && <span className="chip chip-accent">Shorts 9:16</span>}
            </div>
            <p className="mt-1 truncate font-mono text-[10.5px] text-[#79776f]">
              {preview
                ? `${preview.video_size_mb} MB · ${preview.video_info.duration}s · ${preview.video_info.width}×${preview.video_info.height}`
                : target}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="btn btn-xs btn-ghost shrink-0 hover:bg-white/10"
            aria-label="Close dialog"
          >
            Close
          </button>
        </div>

        {/* Content View */}
        {loading ? (
          <div className="flex flex-1 min-h-[240px] items-center justify-center p-8 text-center text-[12px] text-[#79776f]">
            <div className="space-y-2.5">
              <span className="pulse-dot inline-block h-3 w-3 rounded-full bg-[#e5a183]" />
              <p>Generating SEO title, hashtags, and tags, and checking channel connections...</p>
            </div>
          </div>
        ) : job ? (
          <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
            <div className="flex-1 min-h-0 overflow-y-auto p-5 space-y-4">
              <div className="panel-inset space-y-4 p-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12.5px] font-medium text-white">
                    {job.status === "UPLOADING"
                      ? "Uploading to YouTube..."
                      : job.status === "DONE"
                        ? "✅ Upload complete!"
                        : "Upload failed"}
                  </span>
                  <span className="font-mono text-[11px] text-[#e5a183]">{job.progress}%</span>
                </div>

                <div className="h-2 overflow-hidden rounded-full bg-[#151920]">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${
                      job.status === "ERROR"
                        ? "bg-[#e08a8a]"
                        : job.status === "DONE"
                          ? "bg-[#7fc8a3]"
                          : "bg-[#e5a183]"
                    }`}
                    style={{ width: `${job.progress}%` }}
                  />
                </div>

                {job.error && (
                  <div className="rounded-lg border border-[#e08a8a]/30 bg-[#e08a8a]/8 px-3 py-2 font-mono text-[10.5px] leading-relaxed text-[#e9aaaa]">
                    {job.error}
                  </div>
                )}

                {job.receipt && (
                  <div className="space-y-3 border-t border-[#1a1f28] pt-3">
                    <dl className="space-y-1.5 text-[11.5px]">
                      <div className="flex gap-2">
                        <dt className="w-20 shrink-0 text-[#79776f]">Channel</dt>
                        <dd className="min-w-0 font-medium text-[#9ed6b8]">{job.receipt.channel_title}</dd>
                      </div>
                      <div className="flex gap-2">
                        <dt className="w-20 shrink-0 text-[#79776f]">Title</dt>
                        <dd className="min-w-0 text-[#d8d4cb]">{job.receipt.title}</dd>
                      </div>
                      <div className="flex gap-2">
                        <dt className="w-20 shrink-0 text-[#79776f]">Visibility</dt>
                        <dd className="font-mono uppercase text-[#dbb675]">{job.receipt.privacy_status}</dd>
                      </div>
                      {job.receipt.local_clip_deleted && (
                        <div className="flex gap-2">
                          <dt className="w-20 shrink-0 text-[#79776f]">Disk</dt>
                          <dd className="font-mono text-[#9ed6b8]">
                            ✓ Local clip removed, {job.receipt.freed_mb ?? 0} MB freed
                          </dd>
                        </div>
                      )}
                    </dl>
                    <div className="flex flex-wrap gap-2 pt-1">
                      <a
                        href={job.receipt.studio_url}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn-sm btn-primary"
                      >
                        Open in YouTube Studio ↗
                      </a>
                      <a
                        href={job.receipt.url}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn-sm btn-secondary"
                      >
                        Watch link ↗
                      </a>
                    </div>
                  </div>
                )}
              </div>
            </div>
            <div className="flex shrink-0 items-center justify-end gap-2 border-t border-[#1a1f28] bg-[#0c0f14] px-5 py-3.5">
              <button
                type="button"
                onClick={onClose}
                className="btn btn-sm btn-primary"
              >
                {job.status === "DONE" ? "Done" : "Close"}
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleUpload} className="flex flex-1 min-h-0 flex-col overflow-hidden">
            {/* Scrollable Form Body */}
            <div className="flex-1 min-h-0 overflow-y-auto p-5 space-y-4">
              {/* Channel Routing Lock info */}
              {selectedConnected && selectedSlot?.channel && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#7fc8a3]/25 bg-[#7fc8a3]/7 px-3.5 py-3">
                  <div className="flex min-w-0 items-center gap-2.5">
                    {selectedSlot.channel.thumbnail_url && (
                      <img
                        src={selectedSlot.channel.thumbnail_url}
                        alt={selectedSlot.channel.title}
                        className="h-8 w-8 shrink-0 rounded-full border border-[#7fc8a3]/40"
                      />
                    )}
                    <div className="min-w-0">
                      <p className="text-[9.5px] font-medium uppercase tracking-[0.12em] text-[#9ed6b8]">
                        {selectedProfile === "clipper"
                          ? "Locked to the live clipper channel"
                          : "Locked to the studio channel"}
                      </p>
                      <p className="truncate text-[12.5px] font-medium text-white">
                        {selectedSlot.channel.title}{" "}
                        {selectedSlot.channel.custom_url && (
                          <span className="font-mono text-[10px] font-normal text-[#79776f]">
                            ({selectedSlot.channel.custom_url})
                          </span>
                        )}
                      </p>
                    </div>
                  </div>
                  <span className="chip chip-ok shrink-0">OAuth ready</span>
                </div>
              )}

              {!selectedConnected && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#dbb675]/28 bg-[#dbb675]/7 px-3.5 py-3 text-[11.5px]">
                  <div className="min-w-0">
                    <p className="font-medium text-[#e6c894]">
                      {selectedProfile === "clipper"
                        ? "The live clipper channel is not connected."
                        : "The studio channel is not connected."}
                    </p>
                    <p className="mt-0.5 leading-relaxed text-[#a3a099]">
                      {selectedProfile === "clipper"
                        ? "Clips can only upload to the dedicated clipper channel."
                        : "Studio videos can only upload to the studio channel."}
                    </p>
                  </div>
                  {onOpenConnectTab && (
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        onOpenConnectTab();
                      }}
                      className="btn btn-xs btn-primary shrink-0"
                    >
                      Connect channel
                    </button>
                  )}
                </div>
              )}

              {/* Title input */}
              <div className="field">
                <div className="flex items-center justify-between gap-2">
                  <label className="label" htmlFor="upload-title">
                    Video title
                  </label>
                  <span
                    className={`font-mono text-[10px] ${
                      title.length > 100 ? "text-[#e9aaaa]" : "text-[#79776f]"
                    }`}
                  >
                    {title.length}/100
                  </span>
                </div>
                <input
                  id="upload-title"
                  type="text"
                  required
                  maxLength={100}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="input"
                />
                {preview?.title_options && preview.title_options.length > 1 && (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {preview.title_options.map((opt, idx) => {
                      const active = title.trim() === opt.trim();
                      return (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => setTitle(opt)}
                          aria-pressed={active}
                          className={`max-w-full truncate rounded-lg border px-2.5 py-1 text-left text-[10.5px] transition-colors ${
                            active
                              ? "border-[#e5a183]/50 bg-[#e5a183]/10 text-[#f8d2bd]"
                              : "border-[#222936] bg-[#0b0e13] text-[#a3a099] hover:border-[#333d4c] hover:text-white"
                          }`}
                        >
                          {opt}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Hashtags */}
              <div className="field">
                <label className="label" htmlFor="upload-hashtags">
                  Hashtags · three to six perform best
                </label>
                <input
                  id="upload-hashtags"
                  type="text"
                  value={hashtagsText}
                  onChange={(e) => setHashtagsText(e.target.value)}
                  placeholder="#Shorts #GTAVI #GTA6 #Gaming"
                  className="input font-mono text-[11px]"
                />
              </div>

              {/* Description */}
              <div className="field">
                <label className="label" htmlFor="upload-description">
                  Description · includes chapters, sources, and the AI disclosure
                </label>
                <textarea
                  id="upload-description"
                  rows={5}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="textarea font-mono text-[10.5px]"
                />
              </div>

              {/* Search tags */}
              <div className="field">
                <div className="flex items-center justify-between gap-2">
                  <label className="label" htmlFor="upload-tags">
                    Search tags · comma separated
                  </label>
                  <span
                    className={`font-mono text-[10px] ${
                      tagCharCount > 480 ? "text-[#e6c894]" : "text-[#79776f]"
                    }`}
                  >
                    {parsedTags.length} tags · {tagCharCount}/500
                  </span>
                </div>
                <input
                  id="upload-tags"
                  type="text"
                  value={tagsText}
                  onChange={(e) => setTagsText(e.target.value)}
                  className="input font-mono text-[11px]"
                />
              </div>

              {/* Visibility, Category & Schedule */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="field">
                  <label className="label" htmlFor="upload-privacy">
                    Visibility
                  </label>
                  <select
                    id="upload-privacy"
                    value={privacy}
                    disabled={Boolean(publishAtLocal)}
                    onChange={(e) =>
                      setPrivacy(e.target.value as "private" | "unlisted" | "public")
                    }
                    className="select"
                  >
                    <option value="private">Private draft</option>
                    <option value="unlisted">Unlisted review link</option>
                    <option value="public">Public immediately</option>
                  </select>
                </div>

                <div className="field">
                  <label className="label" htmlFor="upload-category">
                    Category
                  </label>
                  <select
                    id="upload-category"
                    value={categoryId}
                    onChange={(e) => setCategoryId(e.target.value)}
                    className="select"
                  >
                    {CATEGORIES.map(([id, label]) => (
                      <option key={id} value={id}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label className="label" htmlFor="upload-schedule">
                    Schedule publish
                  </label>
                  <input
                    id="upload-schedule"
                    type="datetime-local"
                    value={publishAtLocal}
                    onChange={(e) => setPublishAtLocal(e.target.value)}
                    className="input font-mono text-[11px]"
                  />
                </div>
              </div>

              {/* Rule 4 sign-off and AI disclosure */}
              <div className="panel-inset space-y-2.5 p-3.5">
                <label className="flex cursor-pointer items-start gap-2.5 text-[11.5px] leading-relaxed text-[#d8d4cb]">
                  <input
                    type="checkbox"
                    checked={approveNow}
                    onChange={(e) => setApproveNow(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>
                    <strong className="font-medium text-white">Rule 4 sign-off.</strong> I reviewed
                    this video, its rights clearance, and its metadata, and I approve uploading it to{" "}
                    <strong className="font-medium text-white">
                      {selectedSlot?.channel?.title || selectedProfile}
                    </strong>
                    .
                  </span>
                </label>
                <label className="flex cursor-pointer items-start gap-2.5 text-[11.5px] leading-relaxed text-[#a3a099]">
                  <input
                    type="checkbox"
                    checked={containsSynthetic}
                    onChange={(e) => setContainsSynthetic(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>Declare altered or synthetic media, per the YouTube policy.</span>
                </label>
              </div>

              {err && (
                <div className="rounded-xl border border-[#e08a8a]/30 bg-[#e08a8a]/8 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-[#e9aaaa]">
                  {err}
                </div>
              )}
            </div>

            {/* Fixed Footer with Upload / Cancel Actions */}
            <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-[#1a1f28] bg-[#0c0f14] px-5 py-3.5">
              <div className="min-w-0">
                <p className="truncate font-mono text-[10.5px] text-[#79776f]">
                  {!approveNow
                    ? "Rule 4 owner approval required to publish"
                    : !selectedConnected
                      ? "Channel connection required"
                      : `Target: ${selectedSlot?.channel?.title || selectedProfile}`}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={submitting}
                  className="btn btn-sm btn-ghost"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !selectedConnected || !approveNow}
                  className="btn btn-sm btn-primary"
                >
                  {submitting
                    ? "Starting upload..."
                    : publishAtLocal
                      ? "Schedule upload"
                      : `Upload ${privacy === "public" ? "publicly" : privacy === "unlisted" ? "as unlisted" : "as draft"}`}
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>,
    document.body
  );
}
