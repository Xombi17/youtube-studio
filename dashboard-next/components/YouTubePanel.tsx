import React, { useCallback, useEffect, useState } from "react";
import type { YouTubeProfileKey, YouTubeProfileStatus, YouTubeStatus } from "@/lib/types";

interface Props {
  onStatusChange?: (status: YouTubeStatus) => void;
}

const SLOT_META: Array<{
  key: YouTubeProfileKey;
  title: string;
  subtitle: string;
  badgeColor: string;
}> = [
  {
    key: "studio",
    title: "Vox & Studio Channel",
    subtitle: "Used for Vox-style explainers, Shorts, and rendered studio exports",
    badgeColor: "text-[#E3A484] border-[#E3A484]/40 bg-[#E3A484]/10",
  },
  {
    key: "clipper",
    title: "Live Clipper Channel",
    subtitle: "Dedicated second account/channel for Live Stream Clips & highlights",
    badgeColor: "text-sky-300 border-sky-400/40 bg-sky-500/10",
  },
];

export default function YouTubePanel({ onStatusChange }: Props) {
  const [status, setStatus] = useState<YouTubeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);

  // Credentials form
  const [credMode, setCredMode] = useState<"json" | "manual">("json");
  const [rawJson, setRawJson] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [savingCreds, setSavingCreds] = useState(false);

  // OAuth Login Link per profile
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [authProfile, setAuthProfile] = useState<YouTubeProfileKey>("clipper");
  const [authLoading, setAuthLoading] = useState<YouTubeProfileKey | null>(null);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedRedirect, setCopiedRedirect] = useState(false);

  const fetchStatus = useCallback(
    async (refresh = false) => {
      try {
        const res = await fetch(`/api/youtube/status${refresh ? "?refresh=1" : ""}`);
        if (!res.ok) {
          throw new Error("Studio API needs a quick restart to load /api/youtube/* routes (run ./scripts/start_studio.sh)");
        }
        const data: YouTubeStatus = await res.json();
        setStatus(data);
        onStatusChange?.(data);
        setErr(null);
      } catch (e: unknown) {
        setErr(e instanceof Error ? e.message : "Failed to load YouTube status");
      } finally {
        setLoading(false);
      }
    },
    [onStatusChange]
  );

  useEffect(() => {
    fetchStatus(false);
    const id = setInterval(() => fetchStatus(false), 3000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  // Listen for OAuth callback popup completion message
  useEffect(() => {
    const onMsg = (ev: MessageEvent) => {
      if (ev.data?.type === "youtube_connected") {
        const prof = ev.data?.profile === "clipper" ? "Live Clipper Channel" : "Vox & Studio Channel";
        setAuthUrl(null);
        setInfoMsg(`${prof} connected and refresh token saved!`);
        fetchStatus(true);
      }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [fetchStatus]);

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setRawJson(text);
    setCredMode("json");
  }

  async function handleSaveCredentials(e: React.FormEvent) {
    e.preventDefault();
    setSavingCreds(true);
    setErr(null);
    setInfoMsg(null);
    try {
      const payload =
        credMode === "json"
          ? { raw_json: rawJson }
          : { client_id: clientId.trim(), client_secret: clientSecret.trim() };
      const res = await fetch("/api/youtube/credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed to save credentials");
      setRawJson("");
      setClientSecret("");
      setInfoMsg("Google Cloud OAuth credentials saved to config/youtube_client_secret.json (chmod 600).");
      await fetchStatus(false);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to save credentials");
    } finally {
      setSavingCreds(false);
    }
  }

  async function handleStartOAuth(profile: YouTubeProfileKey, openNewTab = true) {
    setAuthLoading(profile);
    setAuthProfile(profile);
    setErr(null);
    setInfoMsg(null);
    try {
      const res = await fetch("/api/youtube/auth/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed to build OAuth login link");
      setAuthUrl(json.auth_url);
      if (openNewTab && typeof window !== "undefined") {
        window.open(json.auth_url, "_blank", "noopener,noreferrer");
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to start Google login");
    } finally {
      setAuthLoading(null);
    }
  }

  async function handleDisconnect(profile: YouTubeProfileKey) {
    setErr(null);
    setInfoMsg(null);
    await fetch("/api/youtube/disconnect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    });
    setAuthUrl(null);
    setInfoMsg(`Disconnected ${profile === "clipper" ? "Live Clipper" : "Vox & Studio"} channel.`);
    await fetchStatus(false);
  }

  function copyText(text: string, setter: (v: boolean) => void) {
    navigator.clipboard.writeText(text);
    setter(true);
    setTimeout(() => setter(false), 1800);
  }

  const activeUploads = status?.active_uploads || [];
  const completedUploads = status?.uploads || [];
  const redirectUri = status?.redirect_uri || "http://localhost:3000/api/youtube/oauth/callback";

  const studioSlot: YouTubeProfileStatus | undefined = status?.profiles?.studio;
  const clipperSlot: YouTubeProfileStatus | undefined = status?.profiles?.clipper;
  const connectedCount = (studioSlot?.connected ? 1 : 0) + (clipperSlot?.connected ? 1 : 0);

  return (
    <div className="space-y-6">
      {err && (
        <div className="rounded-2xl bg-rose-500/10 border border-rose-500/40 p-4 text-xs text-rose-200">
          <strong>Error:</strong> {err}
        </div>
      )}
      {infoMsg && (
        <div className="rounded-2xl bg-emerald-500/10 border border-emerald-500/40 p-4 text-xs text-emerald-200">
          {infoMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Dual Channel Connections & Cloud OAuth Credentials */}
        <section className="lg:col-span-6 panel p-6 space-y-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <span className="inline-block w-2.5 h-2.5 rounded-full bg-rose-500" />
                YouTube Channels ({connectedCount}/2 Connected)
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Keep your <strong>Vox / Studio</strong> channel clean and route{" "}
                <strong>Live Stream Clips</strong> to a separate dedicated channel.
              </p>
            </div>
            <button
              type="button"
              onClick={() => fetchStatus(true)}
              className="px-3 py-1.5 rounded-lg bg-[#181C23] border border-[#343C4A] text-xs font-mono text-slate-200 hover:text-white cursor-pointer shrink-0"
            >
              Refresh
            </button>
          </div>

          {/* Two Dedicated Channel Slots */}
          <div className="space-y-3">
            {SLOT_META.map((slot) => {
              const slotStatus = status?.profiles?.[slot.key];
              const isConnected = Boolean(slotStatus?.connected && slotStatus.channel);
              const ch = slotStatus?.channel;
              const isBusy = authLoading === slot.key;

              return (
                <div
                  key={slot.key}
                  className={`rounded-2xl bg-[#0A0C10] border p-4 space-y-3 ${
                    isConnected ? "border-emerald-500/35" : "border-[#232934]"
                  }`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-white">{slot.title}</span>
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold border ${slot.badgeColor}`}
                        >
                          {slot.key.toUpperCase()}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5">{slot.subtitle}</p>
                    </div>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold border ${
                        isConnected
                          ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
                          : "bg-slate-800 text-slate-400 border-slate-700"
                      }`}
                    >
                      {loading ? "..." : isConnected ? "CONNECTED" : "NOT CONNECTED"}
                    </span>
                  </div>

                  {isConnected && ch ? (
                    <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-[#171B22]">
                      <div className="flex items-center gap-3">
                        {ch.thumbnail_url ? (
                          <img
                            src={ch.thumbnail_url}
                            alt={ch.title}
                            className="w-10 h-10 rounded-full border border-emerald-400/50"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded-full bg-rose-500/20 border border-rose-500/40 flex items-center justify-center font-semibold text-xs text-rose-300">
                            YT
                          </div>
                        )}
                        <div>
                          <div className="text-sm font-bold text-white">{ch.title}</div>
                          <div className="text-[11px] font-mono text-slate-400">
                            {ch.custom_url || ch.id} ·{" "}
                            <span className="text-emerald-400 font-bold">
                              {ch.subscribers.toLocaleString()} subs
                            </span>{" "}
                            · {ch.video_count} videos
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          disabled={!status?.has_client_secret || Boolean(authLoading)}
                          onClick={() => handleStartOAuth(slot.key, true)}
                          className="px-2.5 py-1.5 rounded-lg bg-[#181C23] border border-[#343C4A] text-[11px] font-mono text-slate-200 hover:text-white cursor-pointer disabled:opacity-40"
                        >
                          {isBusy ? "..." : "Switch"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDisconnect(slot.key)}
                          className="px-2.5 py-1.5 rounded-lg bg-rose-500/15 border border-rose-500/35 text-[11px] font-mono text-rose-300 hover:bg-rose-500/25 cursor-pointer"
                        >
                          Disconnect
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-[#171B22]">
                      <span className="text-[11px] text-slate-400">
                        {status?.has_client_secret
                          ? "Click to open Google account picker & authorize this channel."
                          : "Save your Google Cloud OAuth secret below first."}
                      </span>
                      <button
                        type="button"
                        disabled={!status?.has_client_secret || Boolean(authLoading)}
                        onClick={() => handleStartOAuth(slot.key, true)}
                        className="px-3.5 py-2 rounded-xl bg-[#E3A484] text-slate-950 text-xs font-bold hover:brightness-110 disabled:opacity-40 cursor-pointer"
                      >
                        {isBusy ? "Generating Link..." : `Connect ${slot.title} ↗`}
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Note about adding a second Gmail in GCP Testing mode */}
          <div className="rounded-xl bg-sky-500/10 border border-sky-500/30 px-3.5 py-2.5 text-[11px] text-sky-200/90">
            <strong>Using a different Gmail for your Clips channel?</strong> Make sure that Gmail
            address is also added under{" "}
            <strong>Google Cloud Console → OAuth consent screen → Test users</strong> (if your Cloud
            app is still in Testing mode).
          </div>

          {/* Generated OAuth Link Box */}
          {authUrl && (
            <div className="rounded-xl bg-[#0A0C10] border border-[#8FB0CE]/50 p-3.5 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-mono text-sky-300 font-bold">
                  Google Login Link Ready ({authProfile === "clipper" ? "Live Clipper" : "Vox & Studio"})
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => copyText(authUrl, setCopiedUrl)}
                    className="px-2.5 py-1 rounded-lg bg-[#181C23] text-[11px] font-mono text-slate-200 hover:text-white cursor-pointer"
                  >
                    {copiedUrl ? "Copied!" : "Copy Link"}
                  </button>
                  <a
                    href={authUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="px-2.5 py-1 rounded-lg bg-[#8FB0CE] text-slate-950 text-[11px] font-bold"
                  >
                    Open Login ↗
                  </a>
                </div>
              </div>
              <div className="text-[11px] font-mono text-slate-400 break-all max-h-16 overflow-y-auto">
                {authUrl}
              </div>
            </div>
          )}

          {/* Collapsible Cloud OAuth Client Secret Config */}
          <details
            open={!status?.has_client_secret}
            className="rounded-2xl bg-[#0A0C10] border border-[#232934] p-4 space-y-3"
          >
            <summary className="cursor-pointer flex items-center justify-between text-xs font-bold text-slate-200">
              <span>
                Google Cloud OAuth Client Secret{" "}
                {status?.has_client_secret && (
                  <span className="text-emerald-400 font-mono ml-1.5">
                    ✓ Loaded ({status.project_id})
                  </span>
                )}
              </span>
              <span className="text-[10px] font-mono text-slate-400">
                {status?.has_client_secret ? "Click to replace" : "Required"}
              </span>
            </summary>

            <div className="pt-3 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <code className="px-2 py-1 rounded panel text-[11px] text-sky-300 font-mono">
                    {redirectUri}
                  </code>
                  <button
                    type="button"
                    onClick={() => copyText(redirectUri, setCopiedRedirect)}
                    className="px-2 py-1 rounded bg-[#181C23] text-[10px] font-mono text-slate-300 hover:text-white cursor-pointer"
                  >
                    {copiedRedirect ? "Copied!" : "Copy URI"}
                  </button>
                </div>
                <div className="flex gap-1">
                  {(["json", "manual"] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setCredMode(m)}
                      className={`px-2 py-1 rounded-lg text-[10px] font-mono cursor-pointer ${
                        credMode === m
                          ? "bg-[#8FB0CE] text-slate-950 font-bold"
                          : "bg-[#12151B] text-slate-400 border border-[#232934]"
                      }`}
                    >
                      {m === "json" ? "JSON" : "ID + Secret"}
                    </button>
                  ))}
                </div>
              </div>

              <form onSubmit={handleSaveCredentials} className="space-y-2.5">
                {credMode === "json" ? (
                  <>
                    <input
                      type="file"
                      accept=".json,application/json"
                      onChange={handleFileSelect}
                      className="block w-full text-xs text-slate-300 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-[#181C23] file:text-slate-200 cursor-pointer"
                    />
                    <textarea
                      rows={3}
                      value={rawJson}
                      onChange={(e) => setRawJson(e.target.value)}
                      placeholder='Paste client_secret_*.json contents here'
                      className="w-full rounded-xl bg-[#12151B] border border-[#2A313D] px-3 py-2 text-[11px] font-mono text-slate-200"
                    />
                  </>
                ) : (
                  <div className="grid grid-cols-1 gap-2">
                    <input
                      type="text"
                      value={clientId}
                      onChange={(e) => setClientId(e.target.value)}
                      placeholder="OAuth Client ID"
                      className="w-full rounded-xl bg-[#12151B] border border-[#2A313D] px-3 py-2 text-xs font-mono text-slate-200"
                    />
                    <input
                      type="password"
                      value={clientSecret}
                      onChange={(e) => setClientSecret(e.target.value)}
                      placeholder="OAuth Client Secret"
                      className="w-full rounded-xl bg-[#12151B] border border-[#2A313D] px-3 py-2 text-xs font-mono text-slate-200"
                    />
                  </div>
                )}

                <button
                  type="submit"
                  disabled={
                    savingCreds ||
                    (credMode === "json" ? !rawJson.trim() : !clientId.trim() || !clientSecret.trim())
                  }
                  className="px-4 py-2 rounded-xl bg-[#8FB0CE] text-slate-950 text-xs font-bold hover:brightness-110 disabled:opacity-40 cursor-pointer"
                >
                  {savingCreds ? "Saving..." : "Save Cloud OAuth Credentials"}
                </button>
              </form>
            </div>
          </details>
        </section>

        {/* Right: Active Upload Queue & Completed History */}
        <section className="lg:col-span-6 panel p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-white">YouTube Upload Queue &amp; History</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Auto-routes Studio renders → <strong>Vox Channel</strong> and Live Clips →{" "}
                <strong>Clipper Channel</strong> with SEO hashtags, tags &amp; Rule 5 disclosure.
              </p>
            </div>
            <button
              type="button"
              onClick={() => fetchStatus(false)}
              className="text-xs font-mono text-slate-400 hover:text-white cursor-pointer"
            >
              Refresh
            </button>
          </div>

          {activeUploads.length > 0 && (
            <div className="space-y-2.5">
              <div className="text-[11px] font-mono uppercase tracking-wider text-amber-300">
                Active Upload Jobs ({activeUploads.length})
              </div>
              {activeUploads.map((job) => (
                <div
                  key={job.job_id}
                  className="rounded-xl bg-[#0A0C10] border border-[#2A313D] p-3.5 space-y-2"
                >
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="font-bold text-slate-100 truncate">
                      {job.title}{" "}
                      {job.profile && (
                        <span className="text-[10px] font-mono text-sky-400 ml-1">
                          [{job.profile}]
                        </span>
                      )}
                    </span>
                    <span
                      className={`font-mono font-bold shrink-0 ${
                        job.status === "DONE"
                          ? "text-emerald-400"
                          : job.status === "ERROR"
                            ? "text-rose-400"
                            : "text-[#E3A484]"
                      }`}
                    >
                      {job.status === "UPLOADING" ? `${job.progress}%` : job.status}
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-[#12151B] overflow-hidden">
                    <div
                      className={`h-full transition-all ${
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
                    <div className="text-[11px] font-mono text-rose-300">{job.error}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="space-y-2.5">
            <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
              Uploaded Videos ({completedUploads.length})
            </div>

            {completedUploads.length === 0 ? (
              <div className="rounded-xl bg-[#0A0C10] border border-dashed border-[#232934] p-8 text-center text-xs text-slate-500 space-y-2">
                <p>No videos uploaded to YouTube yet.</p>
                <p className="font-mono text-[11px] text-slate-400">
                  Open any clip in <strong>Live Clipper</strong> or any render in{" "}
                  <strong>Exports &amp; QA</strong> and click <strong>Upload to YouTube</strong>.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5 max-h-[480px] overflow-y-auto pr-1">
                {completedUploads.map((u) => (
                  <div
                    key={u.video_id}
                    className="rounded-xl bg-[#0A0C10] border border-[#1E232C] p-4 space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-bold text-white">{u.title}</div>
                        <div className="text-[11px] font-mono text-slate-400 mt-0.5">
                          {u.channel_title ? `${u.channel_title} · ` : ""}
                          {u.is_short ? "Short" : "Long-form"} ·{" "}
                          <span className="uppercase text-amber-300">{u.privacy_status}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <a
                          href={u.studio_url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg bg-[#E3A484]/20 border border-[#E3A484]/40 text-[#E3A484] text-[11px] font-bold"
                        >
                          Studio ↗
                        </a>
                        <a
                          href={u.url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg bg-[#181C23] border border-[#343C4A] text-sky-300 text-[11px] font-semibold"
                        >
                          Watch ↗
                        </a>
                      </div>
                    </div>
                    {u.hashtags?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {u.hashtags.map((h) => (
                          <span
                            key={h}
                            className="px-2 py-0.5 rounded-md bg-sky-500/10 border border-sky-500/25 text-[10px] font-mono text-sky-300"
                          >
                            {h}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
