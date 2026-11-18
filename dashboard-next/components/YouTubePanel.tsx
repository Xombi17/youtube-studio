import React, { useCallback, useEffect, useState } from "react";
import type { YouTubeProfileKey, YouTubeProfileStatus, YouTubeStatus } from "@/lib/types";

interface Props {
  onStatusChange?: (status: YouTubeStatus) => void;
}

const SLOT_META: Array<{
  key: YouTubeProfileKey;
  title: string;
  subtitle: string;
}> = [
  {
    key: "studio",
    title: "Vox & Studio Channel",
    subtitle: "Used for Vox-style explainers, Shorts, and rendered studio exports",
  },
  {
    key: "clipper",
    title: "Live Clipper Channel",
    subtitle: "Dedicated second account/channel for Live Stream Clips & highlights",
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
    <div className="space-y-5">
      {err && (
        <div className="rounded-xl border border-[#e08a8a]/30 bg-[#e08a8a]/8 px-4 py-3 text-[11.5px] leading-relaxed text-[#e9aaaa]">
          <strong className="font-medium">Connection problem.</strong> {err}
        </div>
      )}
      {infoMsg && (
        <div className="rounded-xl border border-[#7fc8a3]/25 bg-[#7fc8a3]/8 px-4 py-3 text-[11.5px] leading-relaxed text-[#9ed6b8]">
          {infoMsg}
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Channels and credentials */}
        <section className="panel lg:col-span-6">
          <div className="panel-head">
            <div>
              <h2 className="panel-title">YouTube channels</h2>
              <p className="panel-sub">
                {connectedCount} of 2 connected. Studio renders and live clips use separate channels.
              </p>
            </div>
            <button type="button" onClick={() => fetchStatus(true)} className="btn btn-xs btn-ghost">
              Refresh
            </button>
          </div>

          <div className="space-y-4 p-5">
            <div className="space-y-3">
              {SLOT_META.map((slot) => {
                const slotStatus = status?.profiles?.[slot.key];
                const isConnected = Boolean(slotStatus?.connected && slotStatus.channel);
                const ch = slotStatus?.channel;
                const isBusy = authLoading === slot.key;

                return (
                  <div
                    key={slot.key}
                    className={`rounded-xl border p-3.5 ${
                      isConnected ? "border-[#7fc8a3]/28 bg-[#0b0e13]" : "border-[#1a1f28] bg-[#0b0e13]"
                    }`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[13px] font-medium text-white">{slot.title}</span>
                          <span className="chip chip-neutral font-mono uppercase">{slot.key}</span>
                        </div>
                        <p className="mt-0.5 text-[11px] leading-relaxed text-[#79776f]">{slot.subtitle}</p>
                      </div>
                      <span
                        className={`chip shrink-0 ${
                          isConnected ? "chip-ok" : "chip-neutral"
                        }`}
                      >
                        {loading ? "Checking" : isConnected ? "Connected" : "Not connected"}
                      </span>
                    </div>

                    {isConnected && ch ? (
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-[#1a1f28] pt-3">
                        <div className="flex min-w-0 items-center gap-2.5">
                          {ch.thumbnail_url ? (
                            <img
                              src={ch.thumbnail_url}
                              alt={ch.title}
                              className="h-9 w-9 shrink-0 rounded-full border border-[#7fc8a3]/40"
                            />
                          ) : (
                            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-[#222936] bg-[#151920] text-[10px] font-medium text-[#a3a099]">
                              YT
                            </span>
                          )}
                          <div className="min-w-0">
                            <p className="truncate text-[12.5px] font-medium text-[#ecebe6]">{ch.title}</p>
                            <p className="mt-0.5 truncate font-mono text-[10px] text-[#79776f]">
                              {ch.custom_url || ch.id} · {ch.subscribers.toLocaleString()} subs ·{" "}
                              {ch.video_count} videos
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            disabled={!status?.has_client_secret || Boolean(authLoading)}
                            onClick={() => handleStartOAuth(slot.key, true)}
                            className="btn btn-xs btn-ghost"
                          >
                            {isBusy ? "Switching" : "Switch"}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDisconnect(slot.key)}
                            className="btn btn-xs btn-danger"
                          >
                            Disconnect
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-[#1a1f28] pt-3">
                        <span className="max-w-[34ch] text-[11px] leading-relaxed text-[#79776f]">
                          {status?.has_client_secret
                            ? "Open the Google account picker to authorize this channel."
                            : "Save the Google Cloud OAuth secret below first."}
                        </span>
                        <button
                          type="button"
                          disabled={!status?.has_client_secret || Boolean(authLoading)}
                          onClick={() => handleStartOAuth(slot.key, true)}
                          className="btn btn-xs btn-primary"
                        >
                          {isBusy ? "Generating link" : `Connect ${slot.key}`}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="rounded-xl border border-[#9dbbcf]/22 bg-[#9dbbcf]/6 px-3.5 py-2.5 text-[11px] leading-relaxed text-[#b9d0de]">
              Using a different Gmail for the clips channel? Add that address under{" "}
              <span className="font-medium">Google Cloud Console, OAuth consent screen, Test users</span>{" "}
              while the app is still in testing mode.
            </div>

            {authUrl && (
              <div className="panel-inset space-y-2 p-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-[10.5px] text-[#9dbbcf]">
                    Login link ready · {authProfile === "clipper" ? "Live Clipper" : "Vox and Studio"}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => copyText(authUrl, setCopiedUrl)}
                      className="btn btn-xs btn-ghost"
                    >
                      {copiedUrl ? "Copied" : "Copy link"}
                    </button>
                    <a
                      href={authUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="btn btn-xs btn-primary"
                    >
                      Open login ↗
                    </a>
                  </div>
                </div>
                <p className="max-h-16 overflow-y-auto break-all font-mono text-[10px] leading-relaxed text-[#79776f]">
                  {authUrl}
                </p>
              </div>
            )}

            <details
              open={!status?.has_client_secret}
              className="panel-inset p-3.5"
            >
              <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2 text-[12px] font-medium text-[#d8d4cb]">
                <span>
                  Google Cloud OAuth client secret{" "}
                  {status?.has_client_secret && (
                    <span className="ml-1 font-mono text-[10px] font-normal text-[#9ed6b8]">
                      loaded · {status.project_id}
                    </span>
                  )}
                </span>
                <span className="font-mono text-[10px] font-normal text-[#79776f]">
                  {status?.has_client_secret ? "Replace" : "Required"}
                </span>
              </summary>

              <div className="space-y-3 pt-3">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="truncate rounded-md border border-[#1a1f28] bg-[#0b0e13] px-2 py-1 font-mono text-[10px] text-[#9dbbcf]">
                    {redirectUri}
                  </code>
                  <button
                    type="button"
                    onClick={() => copyText(redirectUri, setCopiedRedirect)}
                    className="btn btn-xs btn-ghost"
                  >
                    {copiedRedirect ? "Copied" : "Copy URI"}
                  </button>
                  <div className="seg ml-auto">
                    {(["json", "manual"] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        aria-pressed={credMode === m}
                        onClick={() => setCredMode(m)}
                      >
                        {m === "json" ? "JSON" : "ID and secret"}
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
                        aria-label="OAuth client secret JSON file"
                        className="block w-full cursor-pointer text-[11px] text-[#a3a099] file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-[#1b2029] file:px-3 file:py-1.5 file:text-[11px] file:font-medium file:text-[#ecebe6]"
                      />
                      <textarea
                        rows={3}
                        value={rawJson}
                        onChange={(e) => setRawJson(e.target.value)}
                        placeholder="Paste the client_secret JSON contents here"
                        aria-label="OAuth client secret JSON"
                        className="textarea font-mono text-[10.5px]"
                      />
                    </>
                  ) : (
                    <div className="grid grid-cols-1 gap-2">
                      <input
                        type="text"
                        value={clientId}
                        onChange={(e) => setClientId(e.target.value)}
                        placeholder="OAuth client ID"
                        aria-label="OAuth client ID"
                        className="input font-mono text-[11px]"
                      />
                      <input
                        type="password"
                        value={clientSecret}
                        onChange={(e) => setClientSecret(e.target.value)}
                        placeholder="OAuth client secret"
                        aria-label="OAuth client secret"
                        className="input font-mono text-[11px]"
                      />
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={
                      savingCreds ||
                      (credMode === "json" ? !rawJson.trim() : !clientId.trim() || !clientSecret.trim())
                    }
                    className="btn btn-sm btn-secondary"
                  >
                    {savingCreds ? "Saving" : "Save OAuth credentials"}
                  </button>
                </form>
              </div>
            </details>
          </div>
        </section>

        {/* Uploads */}
        <section className="panel lg:col-span-6">
          <div className="panel-head">
            <div>
              <h2 className="panel-title">Upload queue</h2>
              <p className="panel-sub">
                Studio renders go to the studio channel, live clips to the clipper channel.
              </p>
            </div>
            <button type="button" onClick={() => fetchStatus(false)} className="btn btn-xs btn-ghost">
              Refresh
            </button>
          </div>

          <div className="space-y-4 p-5">
            {activeUploads.length > 0 && (
              <div className="space-y-2">
                <p className="label">Active jobs · {activeUploads.length}</p>
                {activeUploads.map((job) => (
                  <div key={job.job_id} className="panel-inset space-y-2 p-3.5">
                    <div className="flex items-center justify-between gap-2 text-[11.5px]">
                      <span className="truncate font-medium text-[#ecebe6]">
                        {job.title}
                        {job.profile && (
                          <span className="ml-1.5 font-mono text-[10px] text-[#79776f]">
                            [{job.profile}]
                          </span>
                        )}
                      </span>
                      <span
                        className={`shrink-0 font-mono text-[10.5px] ${
                          job.status === "DONE"
                            ? "text-[#9ed6b8]"
                            : job.status === "ERROR"
                              ? "text-[#e9aaaa]"
                              : "text-[#e5a183]"
                        }`}
                      >
                        {job.status === "UPLOADING" ? `${job.progress}%` : job.status}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[#151920]">
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
                      <p className="font-mono text-[10.5px] leading-relaxed text-[#e9aaaa]">{job.error}</p>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-2">
              <p className="label">Uploaded · {completedUploads.length}</p>

              {completedUploads.length === 0 ? (
                <div className="rounded-xl border border-dashed border-[#222936] px-4 py-12 text-center text-[11.5px] leading-relaxed text-[#79776f]">
                  Nothing uploaded yet.
                  <br />
                  Open a clip in Live Clipper or an export in Exports and QA, then choose Upload to YouTube.
                </div>
              ) : (
                <div className="max-h-[500px] space-y-2 overflow-y-auto pr-1">
                  {completedUploads.map((u) => (
                    <div key={u.video_id} className="panel-inset space-y-2 p-3.5">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-[12.5px] font-medium text-[#ecebe6]">{u.title}</p>
                          <p className="mt-0.5 font-mono text-[10px] text-[#79776f]">
                            {u.channel_title ? `${u.channel_title} · ` : ""}
                            {u.is_short ? "Short" : "Long-form"} ·{" "}
                            <span className="uppercase text-[#dbb675]">{u.privacy_status}</span>
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-1.5">
                          <a
                            href={u.studio_url}
                            target="_blank"
                            rel="noreferrer"
                            className="btn btn-xs btn-ghost"
                          >
                            Studio ↗
                          </a>
                          <a href={u.url} target="_blank" rel="noreferrer" className="btn btn-xs btn-secondary">
                            Watch ↗
                          </a>
                        </div>
                      </div>
                      {u.hashtags?.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {u.hashtags.map((h) => (
                            <span
                              key={h}
                              className="rounded-md border border-[#1a1f28] bg-[#101319] px-1.5 py-0.5 font-mono text-[9.5px] text-[#9dbbcf]"
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
          </div>
        </section>
      </div>
    </div>
  );
}

