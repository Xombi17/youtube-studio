import React, { useEffect, useState } from "react";
import type { ProjectDetail, ProjectSummary } from "@/lib/types";
import YouTubeUploadModal from "@/components/YouTubeUploadModal";

interface Props {
  projects: ProjectSummary[];
  initialSlug?: string | null;
  onRefresh: () => void;
  onOpenYouTubeTab?: () => void;
}

export default function ExportsReview({ projects, initialSlug, onRefresh, onOpenYouTubeTab }: Props) {
  const [selectedSlug, setSelectedSlug] = useState<string | null>(
    initialSlug || projects[0]?.slug || null
  );
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [docTab, setDocTab] = useState<"qa" | "metadata" | "script" | "checklist">("qa");
  const [copied, setCopied] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);

  useEffect(() => {
    if (initialSlug) setSelectedSlug(initialSlug);
    else if (!selectedSlug && projects.length > 0) setSelectedSlug(projects[0].slug);
  }, [initialSlug, projects, selectedSlug]);

  useEffect(() => {
    if (!selectedSlug) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetch(`/api/projects/${encodeURIComponent(selectedSlug)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedSlug, projects]);

  async function toggleApproval(approved: boolean) {
    if (!detail) return;
    await fetch(`/api/projects/${encodeURIComponent(detail.slug)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved }),
    });
    onRefresh();
    const fresh = await fetch(`/api/projects/${encodeURIComponent(detail.slug)}`).then((r) =>
      r.json()
    );
    setDetail(fresh);
  }

  function copyMetadata() {
    if (!detail?.metadata_md) return;
    navigator.clipboard.writeText(detail.metadata_md);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  const approvedCount = projects.filter((p) => p.human_approved).length;

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
      {/* Export list */}
      <aside className="panel flex flex-col lg:col-span-4">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Rendered exports</h2>
            <p className="panel-sub">
              {projects.length} total · {approvedCount} signed off
            </p>
          </div>
          <button type="button" onClick={onRefresh} className="btn btn-xs btn-ghost">
            Refresh
          </button>
        </div>

        <div className="max-h-[680px] space-y-1 overflow-y-auto p-2.5">
          {projects.map((p) => {
            const active = p.slug === selectedSlug;
            return (
              <button
                key={p.slug}
                type="button"
                onClick={() => setSelectedSlug(p.slug)}
                aria-current={active ? "true" : undefined}
                className={`relative w-full rounded-xl px-3 py-2.5 text-left transition-colors ${
                  active ? "bg-[#e5a183]/09" : "hover:bg-white/[0.035]"
                }`}
              >
                {active && (
                  <span className="absolute left-0 top-2.5 bottom-2.5 w-[2px] rounded-full bg-[#e5a183]" />
                )}
                <div className="flex items-start justify-between gap-2">
                  <span className="line-clamp-2 text-[12.5px] font-medium leading-snug text-[#ecebe6]">
                    {p.topic}
                  </span>
                  <span
                    className={`chip shrink-0 ${
                      p.qa_passed ? "chip-ok" : "chip-warn"
                    }`}
                  >
                    {p.qa_verdict || "READY"}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center justify-between gap-2 font-mono text-[10.5px] text-[#79776f]">
                  <span className="truncate">
                    {p.format === "long" ? "16:9" : "9:16"} · {p.style?.id || "custom"}
                  </span>
                  <span className={p.human_approved ? "text-[#7fc8a3]" : "text-[#dbb675]"}>
                    {p.human_approved ? "Approved" : "Needs sign-off"}
                  </span>
                </div>
              </button>
            );
          })}
          {projects.length === 0 && (
            <div className="px-3 py-14 text-center text-[12px] leading-relaxed text-[#79776f]">
              No rendered exports yet.
              <br />
              Launch a render from the Production tab.
            </div>
          )}
        </div>
      </aside>

      {/* Inspector */}
      <section className="panel lg:col-span-8">
        {!detail ? (
          <div className="flex h-[520px] items-center justify-center px-6 text-center text-[12.5px] leading-relaxed text-[#79776f]">
            {loading
              ? "Loading export package"
              : "Select an export to inspect the video, QA findings, and prepared metadata."}
          </div>
        ) : (
          <div>
            {/* Header */}
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#1a1f28] px-5 py-4">
              <div className="min-w-0">
                <h2 className="text-[17px] font-semibold tracking-[-0.02em] text-white">
                  {detail.topic}
                </h2>
                <p className="mt-1 truncate font-mono text-[10.5px] text-[#79776f]">
                  exports/{detail.slug}/{detail.video || "no video"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {detail.youtube_upload ? (
                  <a
                    href={detail.youtube_upload.studio_url}
                    target="_blank"
                    rel="noreferrer"
                    className="chip chip-danger h-[30px]"
                  >
                    Uploaded · {detail.youtube_upload.privacy_status} ↗
                  </a>
                ) : null}
                {detail.video && (
                  <button
                    type="button"
                    onClick={() => setUploadOpen(true)}
                    className="btn btn-sm btn-secondary"
                  >
                    {detail.youtube_upload ? "Re-upload" : "Upload to YouTube"}
                  </button>
                )}
                {detail.human_approved ? (
                  <button
                    type="button"
                    onClick={() => toggleApproval(false)}
                    className="btn btn-sm btn-ghost"
                  >
                    Revoke approval
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => toggleApproval(true)}
                    className="btn btn-sm btn-primary"
                  >
                    Sign off for upload
                  </button>
                )}
              </div>
            </div>

            <div className="space-y-5 p-5">
              {detail.human_approved && (
                <div className="flex items-center gap-2 rounded-xl border border-[#7fc8a3]/25 bg-[#7fc8a3]/08 px-3.5 py-2.5 text-[11.5px] text-[#9ed6b8]">
                  Signed off by the channel owner. Upload manually or hand it to the YouTube panel.
                </div>
              )}

              {/* Preview + telemetry */}
              <div className="grid grid-cols-1 items-start gap-5 md:grid-cols-12">
                <div className="flex justify-center rounded-xl border border-[#1a1f28] bg-[#0b0e13] p-3 md:col-span-5">
                  {detail.video_url ? (
                    <video
                      key={detail.video_url}
                      src={detail.video_url}
                      controls
                      playsInline
                      className={`rounded-lg bg-black ${
                        detail.format === "short" ? "max-h-[420px] aspect-[9/16]" : "w-full aspect-video"
                      }`}
                    />
                  ) : (
                    <div className="py-24 text-[11.5px] text-[#79776f]">No MP4 found</div>
                  )}
                </div>

                <div className="space-y-4 md:col-span-7">
                  <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-[#1a1f28] bg-[#1a1f28] sm:grid-cols-3">
                    <Telemetry
                      label="Resolution"
                      value={detail.review?.metrics.resolution || detail.resolution || "None"}
                    />
                    <Telemetry
                      label="Framerate"
                      value={detail.review?.metrics.fps ? `${detail.review.metrics.fps} fps` : "None"}
                    />
                    <Telemetry
                      label="Duration"
                      value={detail.review?.metrics.duration ? `${detail.review.metrics.duration}s` : "None"}
                    />
                    <Telemetry
                      label="Loudness"
                      value={
                        detail.review?.metrics.loudness_lufs != null
                          ? `${detail.review.metrics.loudness_lufs} LUFS`
                          : "None"
                      }
                    />
                    <Telemetry
                      label="True peak"
                      value={
                        detail.review?.metrics.true_peak_dbtp != null
                          ? `${detail.review.metrics.true_peak_dbtp} dBTP`
                          : "None"
                      }
                    />
                    <Telemetry
                      label="Kinetic motion"
                      value={detail.review?.metrics.motion_verified ? "Verified" : "Unchecked"}
                      tone={detail.review?.metrics.motion_verified ? "ok" : "warn"}
                    />
                  </dl>

                  {detail.frames && detail.frames.length > 0 && (
                    <div>
                      <p className="label mb-2">Sampled beat frames ({detail.frames.length})</p>
                      <div className="flex gap-2 overflow-x-auto pb-1">
                        {detail.frames.map((src) => (
                          <img
                            key={src}
                            src={src}
                            alt="Beat frame"
                            className="h-24 shrink-0 rounded-lg border border-[#222936] object-cover"
                          />
                        ))}
                      </div>
                    </div>
                  )}

                  <p className="rounded-xl border border-[#1a1f28] bg-[#151920] px-3.5 py-2.5 text-[11.5px] leading-relaxed text-[#a3a099]">
                    <strong className="font-medium text-[#d8d4cb]">Rule 4:</strong> CreatorRadar never
                    auto-uploads. Review the video, sign off here, then publish with the prepared{" "}
                    <code className="font-mono text-[11px]">metadata.md</code>.
                  </p>
                </div>
              </div>

              {/* Docs */}
              <div>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div className="seg">
                    {(["qa", "metadata", "script", "checklist"] as const).map((t) => (
                      <button
                        key={t}
                        type="button"
                        aria-pressed={docTab === t}
                        onClick={() => setDocTab(t)}
                        className="uppercase tracking-[0.08em]"
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                  {docTab === "metadata" && detail.metadata_md && (
                    <button type="button" onClick={copyMetadata} className="btn btn-xs btn-secondary">
                      {copied ? "Copied" : "Copy metadata"}
                    </button>
                  )}
                </div>

                {docTab === "qa" && detail.review && (
                  <div className="space-y-3">
                    {detail.review.findings.length > 0 && (
                      <div className="space-y-1.5">
                        {detail.review.findings.map((f, i) => (
                          <div
                            key={i}
                            className="rounded-lg border border-[#e08a8a]/25 bg-[#e08a8a]/08 px-3 py-2 text-[11.5px] text-[#e9aaaa]"
                          >
                            <strong className="font-mono text-[10px] uppercase tracking-wide">
                              {f.severity}
                            </strong>
                            <span className="ml-2">{f.issue}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="overflow-hidden rounded-xl border border-[#1a1f28]">
                      {detail.review.compliance.map((c, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between gap-4 border-b border-[#1a1f28] px-3.5 py-3 text-[12px] last:border-b-0"
                        >
                          <div className="min-w-0">
                            <div className="font-medium text-[#ecebe6]">{c.rule}</div>
                            <div className="mt-0.5 text-[11px] leading-relaxed text-[#79776f]">
                              {c.detail}
                            </div>
                          </div>
                          <span
                            className={`chip shrink-0 ${
                              c.status === "PASS" || c.status === "APPROVED"
                                ? "chip-ok"
                                : c.status === "FAIL"
                                  ? "chip-danger"
                                  : "chip-warn"
                            }`}
                          >
                            {c.status}
                          </span>
                        </div>
                      ))}
                      {detail.review.compliance.length === 0 && (
                        <p className="px-3.5 py-6 text-center text-[11.5px] text-[#79776f]">
                          No compliance rows were recorded for this export.
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {docTab === "qa" && !detail.review && (
                  <p className="rounded-xl border border-dashed border-[#222936] px-3.5 py-10 text-center text-[11.5px] text-[#79776f]">
                    No QA report was generated for this export.
                  </p>
                )}

                {docTab === "metadata" && (
                  <pre className="code-block whitespace-pre-wrap">
                    {detail.metadata_md || "No metadata.md generated."}
                  </pre>
                )}

                {docTab === "script" && (
                  <pre className="code-block whitespace-pre-wrap">
                    {detail.script_md || "No script.md found in renders/."}
                  </pre>
                )}

                {docTab === "checklist" && (
                  <pre className="code-block whitespace-pre-wrap">
                    {detail.checklist_md || "No checklist.md generated."}
                  </pre>
                )}
              </div>
            </div>
          </div>
        )}
      </section>

      {uploadOpen && detail && (
        <YouTubeUploadModal
          target={detail.slug}
          targetType="project"
          onClose={() => setUploadOpen(false)}
          onUploaded={onRefresh}
          onOpenConnectTab={onOpenYouTubeTab}
        />
      )}
    </div>
  );
}

function Telemetry({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn";
}) {
  const color =
    tone === "ok" ? "text-[#9ed6b8]" : tone === "warn" ? "text-[#dbb675]" : "text-[#ecebe6]";
  return (
    <div className="bg-[#0b0e13] px-3.5 py-3">
      <dt className="text-[9.5px] font-medium uppercase tracking-[0.12em] text-[#79776f]">
        {label}
      </dt>
      <dd className={`mt-1 font-mono text-[12px] ${color}`}>{value}</dd>
    </div>
  );
}
