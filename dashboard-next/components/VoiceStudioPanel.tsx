import React, { useRef, useState } from "react";
import type { StudioStatus } from "@/lib/types";

interface Props {
  status: StudioStatus | null;
  onRefresh: () => void;
}

export default function VoiceStudioPanel({ status, onRefresh }: Props) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState(
    "CreatorRadar Studio check. Mastered broadcast narration locked to minus fourteen LUFS."
  );
  const [previewAudio, setPreviewAudio] = useState<string | null>(null);
  const [previewEngine, setPreviewEngine] = useState<string | null>(null);
  const [synthesizing, setSynthesizing] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function toggleRecording() {
    if (!recording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mr = new MediaRecorder(stream);
        chunksRef.current = [];
        mr.ondataavailable = (e) => {
          if (e.data.size > 0) chunksRef.current.push(e.data);
        };
        mr.onstop = async () => {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          setUploadMsg("Converting and saving 48kHz stereo WAV to assets/voices/creator_sample.wav");
          const res = await fetch("/api/upload-voice", { method: "POST", body: blob });
          const data = await res.json();
          setUploadMsg(data.message || data.error || "Saved.");
          onRefresh();
        };
        mr.start();
        recorderRef.current = mr;
        setRecording(true);
        setSeconds(0);
        timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
      } catch (err) {
        setUploadMsg(`Microphone access failed: ${err instanceof Error ? err.message : String(err)}`);
      }
    } else {
      recorderRef.current?.stop();
      recorderRef.current?.stream.getTracks().forEach((t) => t.stop());
      if (timerRef.current) clearInterval(timerRef.current);
      setRecording(false);
    }
  }

  async function synthesizePreview() {
    if (!previewText.trim()) return;
    setSynthesizing(true);
    try {
      const res = await fetch("/api/voice/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: previewText }),
      });
      const data = await res.json();
      if (res.ok) {
        setPreviewAudio(`${data.audio_url}?t=${Date.now()}`);
        setPreviewEngine(data.engine);
      } else {
        setUploadMsg(`Synthesis error: ${data.error}`);
      }
    } finally {
      setSynthesizing(false);
    }
  }

  const vsOnline = status?.voicestudio.online ?? false;

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      {/* Voice profile */}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Creator voice profile</h2>
            <p className="panel-sub">
              Enrolled sample at{" "}
              <code className="font-mono text-[11px] text-[#a3a099]">assets/voices/creator_sample.wav</code>
            </p>
          </div>
          <span className={`chip ${status?.has_voice_sample ? "chip-ok" : "chip-warn"}`}>
            {status?.has_voice_sample ? "Sample enrolled" : "Missing sample"}
          </span>
        </div>

        <div className="space-y-4 p-5">
          {status?.voice_sample_url ? (
            <div className="panel-inset space-y-2.5 p-3.5">
              <div className="flex items-center justify-between gap-3 font-mono text-[10.5px] text-[#79776f]">
                <span className="truncate">creator_sample.wav</span>
                <span>{(status.voice_sample_bytes / (1024 * 1024)).toFixed(2)} MB</span>
              </div>
              <audio controls src={status.voice_sample_url} className="h-10 w-full" />
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-[#222936] px-3.5 py-8 text-center text-[11.5px] leading-relaxed text-[#79776f]">
              No clone reference recorded yet.
              <br />
              Record fifteen to thirty seconds to create one.
            </div>
          )}

          <div className="panel-inset space-y-3 p-3.5">
            <p className="text-[12px] leading-relaxed text-[#a3a099]">
              Record fifteen to thirty seconds of energetic narration in your studio voice. The clone
              replaces the previous reference.
            </p>
            <div className="flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={toggleRecording}
                className={`btn btn-sm ${recording ? "btn-danger" : "btn-primary"}`}
              >
                {recording && <span className="live-ring h-1.5 w-1.5 rounded-full bg-[#e08a8a]" />}
                {recording ? `Stop and save · ${seconds}s` : "Record a sample"}
              </button>
              {recording && (
                <span className="font-mono text-[11px] text-[#79776f]">
                  Listening on the default input
                </span>
              )}
            </div>
            {uploadMsg && (
              <p className="font-mono text-[11px] leading-relaxed text-[#a3a099]">{uploadMsg}</p>
            )}
          </div>

          <p className="hint">
            Rule 6: every render uses the cloned profile. Flat or robotic audio is rejected by QA.
          </p>
        </div>
      </section>

      {/* Engine + preview */}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">VoiceStudio engine</h2>
            <p className="panel-sub">
              {status?.voicestudio.url || "http://localhost:3900"}
            </p>
          </div>
          <span className={`chip ${vsOnline ? "chip-ok" : "chip-neutral"}`}>
            {vsOnline ? "Cloned voice online" : "Edge-TTS fallback"}
          </span>
        </div>

        <div className="space-y-4 p-5">
          {!vsOnline && (
            <div className="panel-inset space-y-2 p-3.5">
              <p className="text-[11.5px] leading-relaxed text-[#dbb675]">
                Start the local GPU server to use the cloned voice:
              </p>
              <pre className="overflow-x-auto rounded-lg bg-[#0b0e13] p-2.5 font-mono text-[10.5px] leading-relaxed text-[#a3a099]">
                cd VoiceStudio && .venv/bin/uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900
              </pre>
            </div>
          )}

          <div className="field">
            <label className="label" htmlFor="voice-preview">
              Test broadcast synthesis · mastered to -14 LUFS
            </label>
            <textarea
              id="voice-preview"
              rows={4}
              value={previewText}
              onChange={(e) => setPreviewText(e.target.value)}
              className="textarea"
            />
          </div>

          <button
            type="button"
            disabled={synthesizing}
            onClick={synthesizePreview}
            className="btn btn-secondary btn-sm"
          >
            {synthesizing ? "Synthesizing and mastering" : "Generate test clip"}
          </button>

          {previewAudio && (
            <div className="panel-inset space-y-2.5 p-3.5">
              <p className="font-mono text-[10.5px] text-[#9ed6b8]">Engine: {previewEngine}</p>
              <audio controls src={previewAudio} className="h-10 w-full" />
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
