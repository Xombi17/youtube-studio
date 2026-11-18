import React, { useState } from "react";

export default function CreatorTools() {
  const [hookText, setHookText] = useState(
    "Do not wait until launch night to check your PS5 storage for GTA VI."
  );
  const [hookResult, setHookResult] = useState<Record<string, unknown> | null>(null);
  const [hookLoading, setHookLoading] = useState(false);

  const [titleText, setTitleText] = useState("GTA VI Needs 212GB on PS5 — Fix Your Storage Now");
  const [thumbText, setThumbText] = useState("212GB WARNING");
  const [titleResult, setTitleResult] = useState<Record<string, unknown> | null>(null);
  const [titleLoading, setTitleLoading] = useState(false);

  async function runHookScore(e: React.FormEvent) {
    e.preventDefault();
    setHookLoading(true);
    try {
      const res = await fetch("/api/tools/hookscore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hook: hookText }),
      });
      const data = await res.json();
      setHookResult(data.result || data);
    } finally {
      setHookLoading(false);
    }
  }

  async function runTitleLint(e: React.FormEvent) {
    e.preventDefault();
    setTitleLoading(true);
    try {
      const res = await fetch("/api/tools/lint-title", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: titleText, thumb: thumbText }),
      });
      const data = await res.json();
      setTitleResult(data.result || data);
    } finally {
      setTitleLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Hook Scorer */}
      <section className="panel p-6 space-y-4">
        <div>
          <h2 className="text-lg font-bold text-white">Hook Scorer</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Powered by <code>skills/yt-script/hookscore.py</code> — weakest-link weighted 0–100 verdict
          </p>
        </div>

        <form onSubmit={runHookScore} className="space-y-3">
          <textarea
            rows={3}
            value={hookText}
            onChange={(e) => setHookText(e.target.value)}
            className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] p-3 text-sm text-slate-100 focus:outline-none focus:border-[#E3A484]"
          />
          <button
            type="submit"
            disabled={hookLoading}
            className="px-4 py-2 rounded-xl text-xs font-bold bg-[#E3A484] text-slate-950 hover:brightness-110 disabled:opacity-50 cursor-pointer"
          >
            {hookLoading ? "Scoring..." : "Score Hook"}
          </button>
        </form>

        {hookResult && (
          <pre className="rounded-xl bg-[#0A0C10] border border-[#232934] p-4 text-xs font-mono text-emerald-300 overflow-x-auto max-h-80">
            {JSON.stringify(hookResult, null, 2)}
          </pre>
        )}
      </section>

      {/* Title + Thumbnail Pairing Linter */}
      <section className="panel p-6 space-y-4">
        <div>
          <h2 className="text-lg font-bold text-white">Title & Thumbnail Pairing Linter</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Powered by <code>skills/yt-package/title.py</code> — checks desktop/mobile truncation & redundancy
          </p>
        </div>

        <form onSubmit={runTitleLint} className="space-y-3">
          <div>
            <label className="block text-[11px] font-mono uppercase text-slate-400 mb-1">
              YouTube Title ({titleText.length} chars)
            </label>
            <input
              type="text"
              value={titleText}
              onChange={(e) => setTitleText(e.target.value)}
              className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3.5 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-[#8FB0CE]"
            />
          </div>
          <div>
            <label className="block text-[11px] font-mono uppercase text-slate-400 mb-1">
              Thumbnail Text Overlay
            </label>
            <input
              type="text"
              value={thumbText}
              onChange={(e) => setThumbText(e.target.value)}
              className="w-full rounded-xl bg-[#0A0C10] border border-[#2A313D] px-3.5 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-[#8FB0CE]"
            />
          </div>
          <button
            type="submit"
            disabled={titleLoading}
            className="px-4 py-2 rounded-xl text-xs font-bold bg-[#8FB0CE] text-slate-950 hover:brightness-110 disabled:opacity-50 cursor-pointer"
          >
            {titleLoading ? "Linting..." : "Lint Pairing"}
          </button>
        </form>

        {titleResult && (
          <pre className="rounded-xl bg-[#0A0C10] border border-[#232934] p-4 text-xs font-mono text-sky-300 overflow-x-auto max-h-80">
            {JSON.stringify(titleResult, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
