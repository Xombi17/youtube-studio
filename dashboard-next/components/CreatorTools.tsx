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
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      {/* Hook scorer */}
      <section className="panel flex flex-col">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Hook scorer</h2>
            <p className="panel-sub">
              Weakest-link weighted verdict from{" "}
              <code className="font-mono text-[11px] text-[#a3a099]">skills/yt-script/hookscore.py</code>
            </p>
          </div>
        </div>

        <form onSubmit={runHookScore} className="flex flex-1 flex-col gap-3 p-5">
          <div className="field flex-1">
            <label className="label" htmlFor="hook-text">
              Opening line
            </label>
            <textarea
              id="hook-text"
              rows={4}
              value={hookText}
              onChange={(e) => setHookText(e.target.value)}
              className="textarea"
            />
          </div>
          <button type="submit" disabled={hookLoading} className="btn btn-sm btn-primary self-start">
            {hookLoading ? "Scoring" : "Score hook"}
          </button>

          {hookResult ? (
            <pre className="code-block max-h-80 whitespace-pre-wrap text-[#a3a099]">
              {JSON.stringify(hookResult, null, 2)}
            </pre>
          ) : (
            <p className="rounded-xl border border-dashed border-[#222936] px-3.5 py-6 text-center text-[11.5px] leading-relaxed text-[#79776f]">
              Score a hook to see its weakest signal and what to fix first.
            </p>
          )}
        </form>
      </section>

      {/* Title and thumbnail linter */}
      <section className="panel flex flex-col">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Title and thumbnail linter</h2>
            <p className="panel-sub">
              Checks desktop and mobile truncation, plus redundancy, via{" "}
              <code className="font-mono text-[11px] text-[#a3a099]">skills/yt-package/title.py</code>
            </p>
          </div>
        </div>

        <form onSubmit={runTitleLint} className="flex flex-1 flex-col gap-3 p-5">
          <div className="field">
            <div className="flex items-center justify-between gap-2">
              <label className="label" htmlFor="lint-title">
                YouTube title
              </label>
              <span className="font-mono text-[10px] text-[#79776f]">{titleText.length}/100</span>
            </div>
            <input
              id="lint-title"
              type="text"
              value={titleText}
              onChange={(e) => setTitleText(e.target.value)}
              className="input"
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="lint-thumb">
              Thumbnail text
            </label>
            <input
              id="lint-thumb"
              type="text"
              value={thumbText}
              onChange={(e) => setThumbText(e.target.value)}
              className="input"
            />
          </div>
          <button type="submit" disabled={titleLoading} className="btn btn-sm btn-primary self-start">
            {titleLoading ? "Linting" : "Lint pairing"}
          </button>

          {titleResult ? (
            <pre className="code-block max-h-80 whitespace-pre-wrap text-[#a3a099]">
              {JSON.stringify(titleResult, null, 2)}
            </pre>
          ) : (
            <p className="rounded-xl border border-dashed border-[#222936] px-3.5 py-6 text-center text-[11.5px] leading-relaxed text-[#79776f]">
              Lint a pairing to catch duplicate wording and truncation before publishing.
            </p>
          )}
        </form>
      </section>
    </div>
  );
}
