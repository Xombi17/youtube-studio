import React, { useMemo, useState } from "react";
import type { ActiveJob, QueueItem, StyleItem } from "@/lib/types";

interface Props {
  queue: QueueItem[];
  styles: StyleItem[];
  activeJobs: ActiveJob[];
  onRefresh: () => void;
  onJobStarted: (slug: string) => void;
}

export default function ProductionStudio({
  queue,
  styles,
  activeJobs,
  onRefresh,
  onJobStarted,
}: Props) {
  const [topic, setTopic] = useState("");
  const [format, setFormat] = useState<"short" | "long">("short");
  const [styleId, setStyleId] = useState("auto");
  const [styleSearch, setStyleSearch] = useState("");
  const [quality, setQuality] = useState<"draft" | "standard" | "high">("high");
  const [sfx, setSfx] = useState(true);
  const [customScript, setCustomScript] = useState("");
  const [showScriptEditor, setShowScriptEditor] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  // New queue idea form
  const [showAddIdea, setShowAddIdea] = useState(false);
  const [newIdeaTopic, setNewIdeaTopic] = useState("");
  const [newIdeaCategory, setNewIdeaCategory] = useState("Tech / AI Explainer");
  const [newIdeaFormat, setNewIdeaFormat] = useState("Short");
  const [newIdeaPriority, setNewIdeaPriority] = useState("HIGH");
  const [newIdeaHook, setNewIdeaHook] = useState("");

  const filteredStyles = useMemo(() => {
    const q = styleSearch.trim().toLowerCase();
    if (!q) return styles.slice(0, 18);
    return styles
      .filter(
        (s) =>
          s.style_id.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q) ||
          s.best_for.toLowerCase().includes(q) ||
          s.mood.toLowerCase().includes(q)
      )
      .slice(0, 24);
  }, [styles, styleSearch]);

  const runningJobs = activeJobs.filter((j) => j.status === "RUNNING");
  const selectedStyle = styles.find((s) => s.style_id === styleId);

  async function launchRender(override?: { topic?: string; format?: "short" | "long" }) {
    const finalTopic = (override?.topic ?? topic).trim();
    if (!finalTopic) {
      setFeedback("Enter a topic or pick one from the queue first.");
      return;
    }
    setSubmitting(true);
    setFeedback(null);
    try {
      const res = await fetch("/api/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: finalTopic,
          format: override?.format ?? format,
          style: styleId,
          quality,
          sfx,
          script_text: customScript.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Render request failed");
      setFeedback(`Render wave started for "${finalTopic}" (${data.job.slug}). Watch live logs below.`);
      onJobStarted(data.job.slug);
      onRefresh();
    } catch (err) {
      setFeedback(`Error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAddIdea(e: React.FormEvent) {
    e.preventDefault();
    if (!newIdeaTopic.trim()) return;
    try {
      const res = await fetch("/api/queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: newIdeaTopic.trim(),
          category: newIdeaCategory,
          format: newIdeaFormat,
          priority: newIdeaPriority,
          hook: newIdeaHook.trim() || "Queued via Studio UI",
        }),
      });
      if (res.ok) {
        setNewIdeaTopic("");
        setNewIdeaHook("");
        setShowAddIdea(false);
        onRefresh();
      }
    } catch {
      // ignore
    }
  }

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
      {/* Launch a render */}
      <section className="panel flex flex-col xl:col-span-5">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Launch a render</h2>
            <p className="panel-sub">Hook, script, style, voice, SFX, encode, then QA.</p>
          </div>
          {runningJobs.length > 0 && (
            <span className="chip chip-warn">
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-[#dbb675]" />
              {runningJobs.length} rendering
            </span>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-4 p-5">
          <div className="field">
            <label className="label" htmlFor="render-topic">
              Video topic
            </label>
            <input
              id="render-topic"
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="GTA VI launch day survival guide"
              className="input"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="field">
              <span className="label">Format</span>
              <div className="seg w-full">
                <button
                  type="button"
                  aria-pressed={format === "short"}
                  onClick={() => setFormat("short")}
                  className="flex-1"
                >
                  9:16 Short
                </button>
                <button
                  type="button"
                  aria-pressed={format === "long"}
                  onClick={() => setFormat("long")}
                  className="flex-1"
                >
                  16:9 Long
                </button>
              </div>
            </div>

            <div className="field">
              <label className="label" htmlFor="render-quality">
                Encode quality
              </label>
              <select
                id="render-quality"
                value={quality}
                onChange={(e) => setQuality(e.target.value as "draft" | "standard" | "high")}
                className="select"
              >
                <option value="high">High, CQ 18 broadcast</option>
                <option value="standard">Standard, CQ 21</option>
                <option value="draft">Draft preview</option>
              </select>
            </div>
          </div>

          {/* Style selection */}
          <div className="field">
            <div className="flex items-center justify-between gap-3">
              <span className="label">Visual style</span>
              <span className="text-[10.5px] text-[#79776f]">
                {styles.length} cataloged
              </span>
            </div>

            <div className="rounded-xl border border-[#1a1f28] bg-[#0b0e13] p-2.5">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={styleSearch}
                  onChange={(e) => setStyleSearch(e.target.value)}
                  placeholder="Search styles"
                  aria-label="Search visual styles"
                  className="input h-8 flex-1 border-transparent bg-transparent px-1 text-[12px] hover:border-transparent"
                />
                <button
                  type="button"
                  onClick={() => setStyleId("auto")}
                  aria-pressed={styleId === "auto"}
                  className={`btn btn-xs ${
                    styleId === "auto" ? "btn-primary" : "btn-ghost border border-[#222936]"
                  }`}
                >
                  Auto-select
                </button>
              </div>

              <div className="mt-2 max-h-40 space-y-0.5 overflow-y-auto pr-1">
                {filteredStyles.map((s) => {
                  const selected = styleId === s.style_id;
                  return (
                    <button
                      key={s.style_id}
                      type="button"
                      onClick={() => setStyleId(s.style_id)}
                      aria-pressed={selected}
                      className={`flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left transition-colors ${
                        selected
                          ? "bg-[#e5a183]/10 text-white"
                          : "text-[#a3a099] hover:bg-white/[0.04] hover:text-[#ecebe6]"
                      }`}
                    >
                      <span className="truncate text-[12px]">{s.name}</span>
                      <span className="flex shrink-0 items-center gap-1">
                        <span
                          className="h-2.5 w-2.5 rounded-[3px] ring-1 ring-white/15"
                          style={{ backgroundColor: s.tokens.bg }}
                        />
                        <span
                          className="h-2.5 w-2.5 rounded-[3px] ring-1 ring-white/15"
                          style={{ backgroundColor: s.tokens.accent }}
                        />
                      </span>
                    </button>
                  );
                })}
                {filteredStyles.length === 0 && (
                  <p className="px-2 py-3 text-[11.5px] text-[#79776f]">No style matches that search.</p>
                )}
              </div>
            </div>
            <p className="hint">
              {styleId === "auto"
                ? "The script is matched to the best fitting style automatically."
                : `Selected: ${selectedStyle?.name || styleId}`}
            </p>
          </div>

          <label className="flex cursor-pointer items-center gap-2.5 text-[12px] text-[#d8d4cb]">
            <input type="checkbox" checked={sfx} onChange={(e) => setSfx(e.target.checked)} />
            Mix beat transition SFX from{" "}
            <code className="font-mono text-[11px] text-[#a3a099]">assets/sfx</code>
          </label>

          <div>
            <button
              type="button"
              onClick={() => setShowScriptEditor((v) => !v)}
              aria-expanded={showScriptEditor}
              className="btn btn-ghost btn-sm -ml-2.5"
            >
              {showScriptEditor ? "Hide custom script" : "Write a custom script"}
            </button>
            {showScriptEditor && (
              <div className="field mt-2">
                <label className="label" htmlFor="render-script">
                  Beats
                </label>
                <textarea
                  id="render-script"
                  rows={6}
                  value={customScript}
                  onChange={(e) => setCustomScript(e.target.value)}
                  placeholder={"## Beat 1: Hook\nYour opening three-second hook\n\n## Beat 2: Core fact\nVerified primary-source fact"}
                  className="textarea font-mono text-[11.5px]"
                />
              </div>
            )}
          </div>

          {feedback && (
            <div
              className={`rounded-xl border px-3.5 py-2.5 text-[11.5px] leading-relaxed ${
                feedback.startsWith("Error")
                  ? "border-[#e08a8a]/30 bg-[#e08a8a]/10 text-[#e9aaaa]"
                  : "border-[#222936] bg-[#151920] text-[#a3a099]"
              }`}
            >
              {feedback}
            </div>
          )}

          <button
            type="button"
            disabled={submitting}
            onClick={() => launchRender()}
            className="btn btn-primary btn-block mt-auto h-10"
          >
            {submitting
              ? "Dispatching pipeline"
              : `Render ${format === "short" ? "9:16 Short" : "16:9 Video"}`}
          </button>
        </div>
      </section>

      {/* Idea queue */}
      <section className="panel flex flex-col xl:col-span-7">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Content ideas</h2>
            <p className="panel-sub">
              Synced with{" "}
              <code className="font-mono text-[11px] text-[#a3a099]">dashboard/ideas-queue.md</code>
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowAddIdea((v) => !v)}
            className={`btn btn-sm ${showAddIdea ? "btn-ghost" : "btn-secondary"}`}
          >
            {showAddIdea ? "Cancel" : "Add idea"}
          </button>
        </div>

        <div className="flex flex-1 flex-col gap-4 p-5">
          {showAddIdea && (
            <form
              onSubmit={handleAddIdea}
              className="panel-inset grid grid-cols-1 gap-3 p-3.5 md:grid-cols-2"
            >
              <div className="field md:col-span-2">
                <label className="label" htmlFor="idea-topic">
                  Topic
                </label>
                <input
                  id="idea-topic"
                  type="text"
                  required
                  value={newIdeaTopic}
                  onChange={(e) => setNewIdeaTopic(e.target.value)}
                  placeholder="What is the video about"
                  className="input"
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="idea-category">
                  Category
                </label>
                <select
                  id="idea-category"
                  value={newIdeaCategory}
                  onChange={(e) => setNewIdeaCategory(e.target.value)}
                  className="select"
                >
                  <option>GTA VI Tutorial</option>
                  <option>GTA VI News</option>
                  <option>Gaming News</option>
                  <option>AI Story / Animation</option>
                  <option>Tech / AI Explainer</option>
                  <option>Green-Screen Commentary</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="field">
                  <label className="label" htmlFor="idea-format">
                    Format
                  </label>
                  <select
                    id="idea-format"
                    value={newIdeaFormat}
                    onChange={(e) => setNewIdeaFormat(e.target.value)}
                    className="select"
                  >
                    <option>Short</option>
                    <option>Long-form</option>
                    <option>Short + Long-form</option>
                  </select>
                </div>
                <div className="field">
                  <label className="label" htmlFor="idea-priority">
                    Priority
                  </label>
                  <select
                    id="idea-priority"
                    value={newIdeaPriority}
                    onChange={(e) => setNewIdeaPriority(e.target.value)}
                    className="select"
                  >
                    <option>HIGH</option>
                    <option>MEDIUM</option>
                    <option>LOW</option>
                  </select>
                </div>
              </div>
              <div className="field md:col-span-2">
                <label className="label" htmlFor="idea-hook">
                  Evidence or search hook
                </label>
                <input
                  id="idea-hook"
                  type="text"
                  value={newIdeaHook}
                  onChange={(e) => setNewIdeaHook(e.target.value)}
                  placeholder="Official source or search angle"
                  className="input"
                />
              </div>
              <button type="submit" className="btn btn-primary btn-sm md:col-span-2">
                Save to queue
              </button>
            </form>
          )}

          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th className="w-16">ID</th>
                  <th>Topic</th>
                  <th className="w-24">Format</th>
                  <th className="w-20">Priority</th>
                  <th className="w-36 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {queue.map((item) => {
                  const isRunning = activeJobs.some(
                    (j) => j.slug === item.slug && j.status === "RUNNING"
                  );
                  const preferLong = item.format.toLowerCase() === "long-form";
                  return (
                    <tr key={item.id}>
                      <td className="font-mono text-[11px] text-[#cb8767] whitespace-nowrap">
                        {item.id}
                      </td>
                      <td>
                        <div className="font-medium text-[#ecebe6]">{item.topic}</div>
                        <div className="mt-0.5 line-clamp-1 text-[11px] text-[#79776f]">
                          {item.category} · {item.hook}
                        </div>
                      </td>
                      <td className="whitespace-nowrap text-[#a3a099]">{item.format}</td>
                      <td>
                        <span
                          className={`chip ${
                            item.priority === "HIGH" ? "chip-danger" : "chip-neutral"
                          }`}
                        >
                          {item.priority}
                        </span>
                      </td>
                      <td>
                        <div className="flex justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => {
                              setTopic(item.topic);
                              setFormat(preferLong ? "long" : "short");
                            }}
                            className="btn btn-xs btn-ghost"
                          >
                            Load
                          </button>
                          <button
                            type="button"
                            disabled={isRunning}
                            onClick={() =>
                              launchRender({
                                topic: item.topic,
                                format: preferLong ? "long" : "short",
                              })
                            }
                            className="btn btn-xs btn-secondary"
                          >
                            {isRunning ? "Rendering" : "Render"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {queue.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-[12px] text-[#79776f]">
                      Nothing queued yet. Add an idea, or confirm the engine is running on port 8080.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
