import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Head from "next/head";
import { Geist, Geist_Mono } from "next/font/google";
import type { LiveClipperStatus, ProjectSummary, QueueItem, StudioStatus, StyleItem, YouTubeStatus } from "@/lib/types";
import ProductionStudio from "@/components/ProductionStudio";
import ExportsReview from "@/components/ExportsReview";
import VoiceStudioPanel from "@/components/VoiceStudioPanel";
import CreatorTools from "@/components/CreatorTools";
import LiveClipperPanel from "@/components/LiveClipperPanel";
import YouTubePanel from "@/components/YouTubePanel";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

type TabId = "clipper" | "production" | "exports" | "youtube" | "voice" | "tools" | "styles";

interface TabMeta {
  id: TabId;
  label: string;
  short: string;
  hint: string;
}

const TABS: TabMeta[] = [
  {
    id: "clipper",
    label: "Live Clipper",
    short: "Clipper",
    hint: "Watch live streams, score every ten-second window, and export only the moments worth posting.",
  },
  {
    id: "production",
    label: "Production",
    short: "Production",
    hint: "Turn an idea into a rendered Short or long-form video with a visual style you choose.",
  },
  {
    id: "exports",
    label: "Exports & QA",
    short: "Exports",
    hint: "Inspect rendered packages, QA findings and metadata, then sign off before anything leaves the studio.",
  },
  {
    id: "youtube",
    label: "YouTube",
    short: "YouTube",
    hint: "Connect the studio and clipper channels. Uploads stay private until a human approves them.",
  },
  {
    id: "voice",
    label: "Voice",
    short: "Voice",
    hint: "Record a fresh clone reference and preview mastered narration before a render uses it.",
  },
  {
    id: "tools",
    label: "Tools",
    short: "Tools",
    hint: "Score a hook and lint a title and thumbnail pairing before you commit production time to them.",
  },
  {
    id: "styles",
    label: "Style Catalog",
    short: "Styles",
    hint: "Browse the motion style catalog and compare each palette token side by side.",
  },
];

const NAV_GROUPS: Array<{ label: string; ids: TabId[] }> = [
  { label: "Studio", ids: ["clipper", "production", "exports", "youtube"] },
  { label: "Resources", ids: ["voice", "styles", "tools"] },
];

export default function StudioHome() {
  const [tab, setTab] = useState<TabId>("clipper");
  const [clipperSummary, setClipperSummary] = useState<LiveClipperStatus | null>(null);
  const [ytSummary, setYtSummary] = useState<YouTubeStatus | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const qTab = params.get("tab") as TabId | null;
    if (qTab && TABS.some((t) => t.id === qTab)) setTab(qTab);
  }, []);

  const [status, setStatus] = useState<StudioStatus | null>(null);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [styles, setStyles] = useState<StyleItem[]>([]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [apiOffline, setApiOffline] = useState(false);
  const [focusedExport, setFocusedExport] = useState<string | null>(null);
  const [catalogFilter, setCatalogFilter] = useState<"all" | "claude-video" | "lemo-opuscar">("all");
  const [catalogQuery, setCatalogQuery] = useState("");
  const [consoleOpen, setConsoleOpen] = useState(false);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [statusRes, queueRes, projectsRes] = await Promise.all([
        fetch("/api/status"),
        fetch("/api/queue"),
        fetch("/api/projects"),
      ]);
      if (!statusRes.ok) throw new Error("API unhealthy");
      const [statusData, queueData, projectsData] = await Promise.all([
        statusRes.json(),
        queueRes.json(),
        projectsRes.json(),
      ]);
      setStatus(statusData);
      setQueue(queueData.items || []);
      setProjects(projectsData.projects || []);
      setApiOffline(false);
    } catch {
      setApiOffline(true);
    }
  }, []);

  // Load the 120-style catalog once
  useEffect(() => {
    fetch("/api/styles")
      .then((r) => (r.ok ? r.json() : { styles: [] }))
      .then((d) => setStyles(d.styles || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 3500);
    return () => clearInterval(interval);
  }, [fetchAll]);

  useEffect(() => {
    if (!consoleOpen) return;
    logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [status?.logs?.length, consoleOpen]);

  const filteredCatalog = useMemo(() => {
    const q = catalogQuery.trim().toLowerCase();
    return styles.filter((s) => {
      if (catalogFilter !== "all" && s.catalog !== catalogFilter) return false;
      if (!q) return true;
      return (
        s.style_id.toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q) ||
        s.best_for.toLowerCase().includes(q) ||
        s.mood.toLowerCase().includes(q)
      );
    });
  }, [styles, catalogFilter, catalogQuery]);

  const runningCount = status?.active_jobs.filter((j) => j.status === "RUNNING").length ?? 0;
  const approvedCount = projects.filter((p) => p.human_approved).length;
  const logs = status?.logs || [];

  const ytProfiles = ytSummary?.profiles ?? status?.youtube?.profiles;
  const studioCh = ytProfiles?.studio?.connected ? ytProfiles.studio.channel?.title : null;
  const clipperCh = ytProfiles?.clipper?.connected ? ytProfiles.clipper.channel?.title : null;
  const youtubeConnected = Boolean(
    studioCh || clipperCh || ytSummary?.connected || status?.youtube?.connected,
  );
  const youtubeLabel = studioCh && clipperCh
    ? `${studioCh} + ${clipperCh}`
    : studioCh
      ? `${studioCh} · clips off`
      : clipperCh
        ? `${clipperCh} · clips only`
        : youtubeConnected
          ? ytSummary?.channel?.title || status?.youtube?.channel?.title || "Connected"
          : "YouTube not connected";

  const activeTab = TABS.find((t) => t.id === tab) ?? TABS[0];

  const countFor = (id: TabId): number | null => {
    if (id === "clipper") return clipperSummary?.clips_count ?? null;
    if (id === "production") return runningCount || null;
    if (id === "exports") return projects.length || null;
    if (id === "styles") return styles.length || null;
    return null;
  };

  const engineOk = !apiOffline;
  const voiceOk = Boolean(status?.voicestudio.online);

  return (
    <>
      <Head>
        <title>CreatorRadar — Studio</title>
        <meta
          name="description"
          content="Autonomous clip and video studio with human-approved publishing."
        />
      </Head>

      <div className={`${geistSans.variable} ${geistMono.variable} min-h-[100dvh] font-sans`}>
        <div className="mx-auto flex w-full max-w-[1560px] gap-6 px-4 py-4 sm:px-6 lg:px-6 lg:py-5">
          {/* ---------------------------------------------------------------- Rail */}
          <aside className="hidden w-[224px] shrink-0 lg:block">
            <div className="sticky top-5 flex max-h-[calc(100dvh-2.5rem)] flex-col gap-7 overflow-y-auto pb-2 pr-1">
              <BrandMark />

              <nav aria-label="Studio sections" className="space-y-6">
                {NAV_GROUPS.map((group) => (
                  <div key={group.label}>
                    <p className="rail-group-label">{group.label}</p>
                    <div className="space-y-0.5">
                      {group.ids.map((id) => {
                        const meta = TABS.find((t) => t.id === id)!;
                        const active = tab === id;
                        const count = countFor(id);
                        return (
                          <button
                            key={id}
                            type="button"
                            onClick={() => setTab(id)}
                            aria-current={active ? "page" : undefined}
                            className="rail-item"
                          >
                            <span className="truncate">{meta.label}</span>
                            {id === "clipper" && clipperSummary?.running && (
                              <span className="pulse-dot h-1.5 w-1.5 shrink-0 rounded-full bg-[#e08a8a]" />
                            )}
                            {id === "youtube" && (
                              <span
                                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                                  youtubeConnected ? "bg-[#7fc8a3]" : "bg-[#3a3936]"
                                }`}
                              />
                            )}
                            {count !== null && <span className="rail-count">{count}</span>}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </nav>

              <div className="mt-auto space-y-3 rounded-xl border border-[#1b2029] bg-[#0d1015] p-3.5">
                <p className="text-[9.5px] font-semibold uppercase tracking-[0.16em] text-[#5f5d57]">
                  Studio health
                </p>
                <StatusLine
                  label="Engine"
                  value={engineOk ? "Port 8080" : "Offline"}
                  tone={engineOk ? "ok" : "danger"}
                />
                <StatusLine
                  label="Encoder"
                  value={status?.hardware.gpu ? status.hardware.gpu.replace("NVIDIA GeForce ", "") : "CPU mode"}
                  tone={status?.hardware.nvenc ? "ok" : "muted"}
                />
                <StatusLine
                  label="Voice"
                  value={voiceOk ? "Cloned" : "Edge-TTS"}
                  tone={voiceOk ? "ok" : "muted"}
                />
                <button
                  type="button"
                  onClick={() => setTab("youtube")}
                  className="w-full rounded-lg border border-[#222936] bg-[#12161c] px-2.5 py-2 text-left text-[11px] leading-snug text-[#a3a099] transition-colors hover:border-[#333d4c] hover:text-white"
                >
                  <span className="block text-[9.5px] font-semibold uppercase tracking-[0.14em] text-[#5f5d57]">
                    Publishing
                  </span>
                  <span className="mt-0.5 block truncate">{youtubeLabel}</span>
                </button>
              </div>

              <p className="px-1 text-[10px] leading-relaxed text-[#514f4b]">
                Studio v{status?.version || "2.0"} · local-first
                <br />
                Every upload requires human approval.
              </p>
            </div>
          </aside>

          {/* ---------------------------------------------------------------- Canvas */}
          <div className="min-w-0 flex-1 space-y-5">
            {/* Mobile identity */}
            <div className="flex items-center justify-between gap-3 lg:hidden">
              <BrandMark compact />
              <button
                type="button"
                onClick={() => setTab("youtube")}
                className="flex min-w-0 items-center gap-2 rounded-full border border-[#222936] bg-[#101319] px-3 py-1.5 text-[11px] text-[#a3a099]"
              >
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    youtubeConnected ? "bg-[#7fc8a3]" : "bg-[#3a3936]"
                  }`}
                />
                <span className="truncate">{youtubeConnected ? "Channels linked" : "Connect YouTube"}</span>
              </button>
            </div>

            {/* Mobile section switch */}
            <nav aria-label="Studio sections" className="lg:hidden">
              <div className="seg w-full overflow-x-auto">
                {TABS.map(({ id, short }) => (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={tab === id}
                    onClick={() => setTab(id)}
                    className="shrink-0"
                  >
                    {short}
                  </button>
                ))}
              </div>
            </nav>

            {/* Page header */}
            <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 rise-in">
              <div className="min-w-0">
                <h1 className="text-[22px] font-semibold tracking-[-0.025em] text-white sm:text-[24px]">
                  {activeTab.label}
                </h1>
                <p className="mt-1 max-w-[62ch] text-[12.5px] leading-relaxed text-[#a3a099]">
                  {activeTab.hint}
                </p>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <StatusPill
                  tone={engineOk ? "ok" : "danger"}
                  label={engineOk ? "Engine running" : "Engine offline"}
                />
                {status?.hardware.nvenc && <StatusPill tone="muted" label="NVENC" />}
                <button
                  type="button"
                  onClick={() => setTab("youtube")}
                  aria-label="Open YouTube channel settings"
                  className="hidden items-center gap-2 rounded-full border border-[#222936] bg-[#101319] px-3 py-1.5 text-[11px] text-[#a3a099] transition-colors hover:border-[#333d4c] hover:text-white sm:inline-flex"
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      youtubeConnected ? "bg-[#7fc8a3]" : "bg-[#3a3936]"
                    }`}
                  />
                  {youtubeLabel}
                </button>
              </div>
            </header>

            {apiOffline && (
              <div
                role="alert"
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#e08a8a]/25 bg-[#e08a8a]/8 px-4 py-3"
              >
                <p className="text-xs leading-relaxed text-[#e9aaaa]">
                  <strong className="font-semibold">The studio engine is not answering on port 8080.</strong>{" "}
                  <span className="text-[#a3a099]">
                    Start it with{" "}
                    <code className="rounded-md bg-black/35 px-1.5 py-0.5 font-mono text-[11px] text-[#ecebe6]">
                      .venv/bin/python dashboard/app.py
                    </code>
                  </span>
                </p>
                <button type="button" onClick={fetchAll} className="btn btn-sm btn-danger">
                  Retry connection
                </button>
              </div>
            )}

            {/* Studio pulse */}
            <section aria-label="Studio overview" className="panel rise-in overflow-hidden">
              <div className="grid grid-cols-2 gap-px bg-[#1a1f28] lg:grid-cols-5">
                <Metric
                  label="Subscribers"
                  value={(status?.subscribers ?? 11000).toLocaleString()}
                  sub="Monetization threshold met"
                />
                <Metric
                  label="Active skills"
                  value={`${status?.skills_count ?? 31}`}
                  sub="Claude and Codex"
                />
                <Metric
                  label="Visual styles"
                  value={`${status?.styles_count ?? 120}`}
                  sub="21 Claude · 99 Lemo"
                />
                <Metric
                  label="Exports"
                  value={`${projects.length}`}
                  sub={`${approvedCount} signed off`}
                />
                <Metric
                  label="Rendering"
                  value={`${runningCount}`}
                  sub={runningCount > 0 ? "In progress now" : status?.has_voice_sample ? "Voice ready" : "No voice sample"}
                  tone={runningCount > 0 ? "warn" : undefined}
                  wide
                />
              </div>
            </section>

            {/* Active view */}
            <main key={tab} className="rise-in">
              {tab === "clipper" && (
                <LiveClipperPanel
                  onStatusChange={setClipperSummary}
                  onOpenYouTubeTab={() => setTab("youtube")}
                />
              )}

              {tab === "production" && (
                <ProductionStudio
                  queue={queue}
                  styles={styles}
                  activeJobs={status?.active_jobs || []}
                  onRefresh={fetchAll}
                  onJobStarted={(slug) => setFocusedExport(slug)}
                />
              )}

              {tab === "exports" && (
                <ExportsReview
                  projects={projects}
                  initialSlug={focusedExport}
                  onRefresh={fetchAll}
                  onOpenYouTubeTab={() => setTab("youtube")}
                />
              )}

              {tab === "youtube" && <YouTubePanel onStatusChange={setYtSummary} />}

              {tab === "voice" && <VoiceStudioPanel status={status} onRefresh={fetchAll} />}

              {tab === "tools" && <CreatorTools />}

              {tab === "styles" && (
                <section className="panel overflow-hidden">
                  <div className="panel-head">
                    <div>
                      <h2 className="panel-title">Visual motion styles</h2>
                      <p className="panel-sub">
                        {filteredCatalog.length} of {styles.length} styles parsed from{" "}
                        <code className="font-mono text-[11px] text-[#a3a099]">styles/*/STYLE.md</code>
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <label className="sr-only" htmlFor="style-filter">
                        Filter styles
                      </label>
                      <input
                        id="style-filter"
                        type="search"
                        value={catalogQuery}
                        onChange={(e) => setCatalogQuery(e.target.value)}
                        placeholder="Filter styles"
                        className="input w-48"
                      />
                      <div className="seg">
                        {(["all", "claude-video", "lemo-opuscar"] as const).map((f) => (
                          <button
                            key={f}
                            type="button"
                            aria-pressed={catalogFilter === f}
                            onClick={() => setCatalogFilter(f)}
                          >
                            {f === "all" ? "All" : f === "claude-video" ? "Claude" : "Lemo"}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="grid max-h-[640px] grid-cols-1 gap-px overflow-y-auto bg-[#1a1f28] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {filteredCatalog.map((s) => (
                      <article
                        key={s.style_id}
                        className="flex flex-col justify-between gap-3 bg-[#101319] p-4 transition-colors duration-200 hover:bg-[#141821]"
                      >
                        <div>
                          <div className="flex items-start justify-between gap-2">
                            <h3 className="truncate text-[13px] font-medium text-[#ecebe6]">{s.name}</h3>
                            <span className="shrink-0 text-[10px] text-[#79776f]">
                              {s.catalog === "claude-video" ? "Claude" : "Lemo"}
                            </span>
                          </div>
                          <p className="mt-0.5 truncate font-mono text-[10px] text-[#79776f]">{s.style_id}</p>
                          {(s.best_for || s.mood) && (
                            <p className="mt-2 line-clamp-2 text-[11.5px] leading-relaxed text-[#a3a099]">
                              {s.best_for || s.mood}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5 border-t border-[#1a1f28] pt-2.5">
                          {[s.tokens.bg, s.tokens.surface, s.tokens.accent, s.tokens.accent2, s.tokens.text].map(
                            (hex, idx) => (
                              <span
                                key={`${hex}-${idx}`}
                                title={hex}
                                className="h-4 w-4 rounded-[4px] ring-1 ring-white/10"
                                style={{ backgroundColor: hex }}
                              />
                            ),
                          )}
                        </div>
                      </article>
                    ))}
                    {filteredCatalog.length === 0 && (
                      <div className="col-span-full bg-[#101319] px-4 py-16 text-center text-xs text-[#79776f]">
                        No styles match that filter.
                      </div>
                    )}
                  </div>
                </section>
              )}
            </main>

            {/* Engine log */}
            <section className="panel overflow-hidden">
              <button
                type="button"
                onClick={() => setConsoleOpen((v) => !v)}
                aria-expanded={consoleOpen}
                className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors duration-200 hover:bg-white/[0.03]"
              >
                <span className="flex min-w-0 items-center gap-3">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#79776f]">
                    Engine log
                  </span>
                  <span className="truncate font-mono text-[11px] text-[#79776f]">
                    {logs.length > 0 ? logs[logs.length - 1].slice(0, 120) : "waiting for the engine"}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-2.5">
                  <span className="num text-[10px] text-[#79776f]">{logs.length}</span>
                  <svg
                    viewBox="0 0 24 24"
                    className={`h-4 w-4 text-[#79776f] transition-transform duration-300 ${
                      consoleOpen ? "rotate-180" : ""
                    }`}
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="m6 9 6 6 6-6"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
              </button>
              {consoleOpen && (
                <div className="max-h-60 overflow-y-auto border-t border-[#1a1f28] bg-[#0b0e13] p-4 font-mono text-[11px] leading-relaxed">
                  {(logs.length ? logs : ["Waiting for the studio engine API."]).map((line, i) => (
                    <div
                      key={i}
                      className={
                        /ERROR|failed|crashed/i.test(line)
                          ? "text-[#e08a8a]"
                          : /Complete|successfully|PASSED/i.test(line)
                            ? "text-[#7fc8a3]"
                            : "text-[#79776f]"
                      }
                    >
                      {line}
                    </div>
                  ))}
                  <div ref={logEndRef} />
                </div>
              )}
            </section>

            <footer className="flex flex-wrap items-center justify-between gap-2 pb-1 text-[10px] text-[#514f4b]">
              <span>CreatorRadar Studio v{status?.version || "2.0"} · local-first</span>
              <span>Every upload requires human approval.</span>
            </footer>
          </div>
        </div>
      </div>
    </>
  );
}

function BrandMark({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-[#2a323e] bg-[#13171e]">
        <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] text-[#e5a183]" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1" opacity="0.45" />
          <circle cx="12" cy="12" r="4.25" stroke="currentColor" strokeWidth="1" opacity="0.8" />
          <path d="M12 12 19 7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          <circle cx="12" cy="12" r="1.5" fill="currentColor" />
        </svg>
      </span>
      <div className="min-w-0">
        <p className="text-[15px] font-semibold leading-tight tracking-[-0.02em] text-white">
          Creator<span className="text-[#e5a183]">Radar</span>
        </p>
        {!compact && (
          <p className="mt-0.5 text-[10.5px] leading-tight text-[#79776f]">Night studio</p>
        )}
      </div>
    </div>
  );
}

function StatusLine({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "ok" | "muted" | "danger";
}) {
  const dot =
    tone === "ok" ? "bg-[#7fc8a3]" : tone === "danger" ? "bg-[#e08a8a]" : "bg-[#3a3936]";
  return (
    <div className="flex items-center justify-between gap-3 text-[11px]">
      <span className="text-[#79776f]">{label}</span>
      <span className="flex min-w-0 items-center gap-1.5 text-[#d8d4cb]">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
        <span className="truncate">{value}</span>
      </span>
    </div>
  );
}

function StatusPill({ tone, label }: { tone: "ok" | "muted" | "danger"; label: string }) {
  const cls =
    tone === "ok" ? "chip chip-ok" : tone === "danger" ? "chip chip-danger" : "chip chip-neutral";
  const dot =
    tone === "ok" ? "bg-[#7fc8a3]" : tone === "danger" ? "bg-[#e08a8a]" : "bg-[#55534e]";
  return (
    <span className={`${cls} h-[27px]`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  );
}

function Metric({
  label,
  value,
  sub,
  tone,
  wide,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "warn";
  wide?: boolean;
}) {
  return (
    <div className={`stat bg-[#101319] ${wide ? "col-span-2 lg:col-span-1" : ""}`}>
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${tone === "warn" ? "text-[#dbb675]" : ""}`}>{value}</div>
      <div className="stat-sub">{sub}</div>
    </div>
  );
}
