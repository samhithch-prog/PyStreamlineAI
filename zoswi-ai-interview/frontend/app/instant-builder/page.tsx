"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";

import { generateInstantBuilderApp } from "../../lib/api";
import type { InstantBuilderGenerateResponse } from "../../lib/types";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type BuilderSpec = Record<string, unknown>;
type BuilderFiles = Record<string, string>;

const QUICK_PROMPTS = [
  "Create an application tracker without login with a modern UI",
  "Build a CRM-style lead tracker with status filters and responsive layout",
  "Generate an expense manager with categories and monthly summary cards",
  "Add a Kanban board, dark mode, and export CSV",
];

function toSlug(value: string) {
  return String(value || "zoswi-app")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "zoswi-app";
}

function getLanguageFromPath(path: string) {
  if (path.endsWith(".py")) return "python";
  if (path.endsWith(".ts") || path.endsWith(".tsx")) return "typescript";
  if (path.endsWith(".js") || path.endsWith(".jsx")) return "javascript";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".css")) return "css";
  if (path.endsWith(".html")) return "html";
  if (path.endsWith(".sql")) return "sql";
  if (path.endsWith(".md")) return "markdown";
  return "text";
}

export default function InstantBuilderPage() {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [previewFullscreen, setPreviewFullscreen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "ZoSwi Instant App Builder is ready. Describe your app and I will generate a live professional preview first, then refine it from your follow-up edits."
    },
    {
      role: "assistant",
      content:
        "Login is included only if you explicitly ask for authentication. By default, your request is generated as a working app flow."
    },
  ]);
  const [spec, setSpec] = useState<BuilderSpec>({});
  const [files, setFiles] = useState<BuilderFiles>({});
  const [previewHtml, setPreviewHtml] = useState("");
  const [zipBase64, setZipBase64] = useState("");
  const [showCode, setShowCode] = useState(false);

  const featureLabels = useMemo(() => {
    const raw = spec.feature_labels;
    if (!Array.isArray(raw)) return [];
    return raw.map((item) => String(item)).filter(Boolean).slice(0, 12);
  }, [spec]);

  const projectTitle = String(spec.title || "zoswi-app");
  const downloadName = `${toSlug(projectTitle)}.zip`;
  const hasGeneratedApp = Boolean(previewHtml && Object.keys(files).length > 0);
  const modeLabel = String(spec.mode || "build+preview");

  function startFreshWorkspace() {
    setSpec({});
    setFiles({});
    setPreviewHtml("");
    setZipBase64("");
    setShowCode(false);
    setPrompt("");
    setError("");
    setMessages([
      {
        role: "assistant",
        content:
          "Fresh workspace is ready. Describe a new app and ZoSwi will generate it with a full live preview."
      }
    ]);
  }

  async function submitPrompt(event: FormEvent) {
    event.preventDefault();
    const cleanPrompt = String(prompt || "").trim();
    if (!cleanPrompt || loading) return;

    setError("");
    setLoading(true);
    setMessages((prev) => [...prev, { role: "user", content: cleanPrompt }]);

    try {
      const response = (await generateInstantBuilderApp({
        prompt: cleanPrompt,
        current_spec: spec,
        current_files: files,
        current_preview_html: previewHtml
      })) as InstantBuilderGenerateResponse;

      setMessages((prev) => [...prev, { role: "assistant", content: String(response.status_text || "").trim() }]);

      if (response.spec && Object.keys(response.spec).length > 0) {
        setSpec(response.spec);
      }
      if (response.files && Object.keys(response.files).length > 0) {
        setFiles(response.files);
      }
      if (typeof response.preview_html === "string") {
        setPreviewHtml(response.preview_html);
      }
      if (typeof response.project_zip_base64 === "string") {
        setZipBase64(response.project_zip_base64);
      }
      if (response.mode === "show_code") {
        setShowCode(true);
      }
      if (response.mode === "build") {
        setShowCode(false);
      }
      if (response.mode === "export_code" && response.project_zip_base64) {
        setShowCode(false);
      }
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : "Unable to generate app.";
      setError(message);
      setMessages((prev) => [...prev, { role: "assistant", content: `Generation failed: ${message}` }]);
    } finally {
      setLoading(false);
      setPrompt("");
    }
  }

  return (
    <main className="relative min-h-screen px-4 py-5 sm:px-6 lg:px-8">
      <div className="pointer-events-none absolute -top-16 left-8 h-52 w-52 rounded-full bg-cyan-400/20 blur-3xl" />
      <div className="pointer-events-none absolute -right-8 top-12 h-64 w-64 rounded-full bg-emerald-400/20 blur-3xl" />

      <section className="panel mx-auto w-full max-w-[1600px] p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-200/85">ZoSwi Builder</p>
            <h1 className="mt-1 font-[var(--font-display)] text-2xl font-semibold text-slate-100 sm:text-3xl">
              Instant App Builder
            </h1>
            <p className="mt-1 max-w-3xl text-sm text-slate-300">
              Full Workspace Mode is active: large live preview + side builder chat for iterative edits.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="ghost-btn" onClick={startFreshWorkspace} disabled={loading}>
              Start New App
            </button>
            <Link href="/login" className="ghost-btn">
              Back to Login
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto mt-5 grid w-full max-w-[1600px] gap-5 lg:grid-cols-[minmax(0,1.65fr)_minmax(370px,0.95fr)]">
        <div className="space-y-5">
          <section className="panel p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="font-[var(--font-display)] text-2xl font-semibold text-slate-100">Live Preview Canvas</h2>
                <p className="mt-1 text-xs uppercase tracking-[0.14em] text-cyan-100/85">
                  Mode: {modeLabel} • Powered by ZoSwi
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {hasGeneratedApp ? (
                  <button type="button" className="ghost-btn" onClick={() => setPreviewFullscreen(true)}>
                    Full Preview
                  </button>
                ) : null}
                {hasGeneratedApp ? (
                  <button type="button" className="ghost-btn" onClick={() => setShowCode((prev) => !prev)}>
                    {showCode ? "Hide Code" : "Show Code"}
                  </button>
                ) : null}
                {zipBase64 ? (
                  <a className="ghost-btn" href={`data:application/zip;base64,${zipBase64}`} download={downloadName}>
                    Download ZIP
                  </a>
                ) : null}
              </div>
            </div>

            {featureLabels.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {featureLabels.map((label) => (
                  <span key={label} className="premium-chip">
                    {label}
                  </span>
                ))}
              </div>
            ) : null}

            <div className="mt-4 overflow-hidden rounded-xl border border-white/20 bg-slate-950/50">
              {previewHtml ? (
                <iframe
                  title="ZoSwi Instant Builder Preview"
                  srcDoc={previewHtml}
                  className="h-[70vh] min-h-[560px] w-full border-0"
                  sandbox="allow-scripts allow-same-origin allow-forms"
                />
              ) : (
                <div className="flex h-[70vh] min-h-[420px] items-center justify-center px-6 text-center text-sm text-slate-300">
                  Your generated app appears here as a full interactive preview after you submit a prompt.
                </div>
              )}
            </div>
          </section>

          {showCode && Object.keys(files).length > 0 ? (
            <section className="panel p-5">
              <h2 className="font-[var(--font-display)] text-2xl font-semibold text-slate-100">Generated Code</h2>
              <div className="mt-4 max-h-[52vh] space-y-3 overflow-y-auto pr-1">
                {Object.entries(files)
                  .sort((a, b) => a[0].localeCompare(b[0]))
                  .map(([path, content]) => (
                    <details key={path} className="rounded-xl border border-white/20 bg-white/5 p-3" open={path === "README.md"}>
                      <summary className="cursor-pointer text-sm font-semibold text-cyan-100">{path}</summary>
                      <pre className="mt-3 overflow-x-auto rounded-lg border border-white/10 bg-slate-950/60 p-3 text-xs leading-5 text-slate-100">
                        <code data-language={getLanguageFromPath(path)}>{content}</code>
                      </pre>
                    </details>
                  ))}
              </div>
            </section>
          ) : null}
        </div>

        <aside className="panel flex h-[84vh] min-h-[640px] flex-col p-5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-[var(--font-display)] text-2xl font-semibold text-slate-100">Builder Chat</h2>
            <span className="premium-chip">Built with ZoSwi</span>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {QUICK_PROMPTS.map((item) => (
              <button
                type="button"
                key={item}
                className="premium-chip transition hover:bg-white/10"
                onClick={() => setPrompt(item)}
                disabled={loading}
              >
                {item}
              </button>
            ))}
          </div>

          <div className="mt-4 flex-1 space-y-3 overflow-y-auto pr-1">
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`rounded-xl border px-3 py-2 text-sm ${
                  message.role === "assistant"
                    ? "border-cyan-200/30 bg-cyan-400/10 text-cyan-50"
                    : "border-white/20 bg-white/10 text-slate-100"
                }`}
              >
                <p className="mb-1 text-xs font-semibold uppercase tracking-[0.08em] opacity-80">
                  {message.role === "assistant" ? "ZoSwi" : "You"}
                </p>
                <p className="whitespace-pre-wrap">{message.content}</p>
              </div>
            ))}
          </div>

          <form onSubmit={submitPrompt} className="mt-4 border-t border-white/15 pt-4">
            <label htmlFor="builderPrompt" className="text-sm font-semibold text-slate-100">
              Prompt edits
            </label>
            <textarea
              id="builderPrompt"
              className="soft-input min-h-[114px] resize-y"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Create an app to store my applications without login, with searchable table and modern cards..."
              disabled={loading}
            />
            <div className="mt-3 flex items-center gap-2">
              <button type="submit" className="primary-btn" disabled={loading || !prompt.trim()}>
                {loading ? "Generating..." : "Generate / Edit App"}
              </button>
            </div>
            {error ? <p className="mt-3 rounded-lg bg-rose-500/20 px-3 py-2 text-sm text-rose-100">{error}</p> : null}
          </form>
        </aside>
      </section>

      {previewFullscreen && previewHtml ? (
        <div className="fixed inset-0 z-[100] bg-slate-950/80 p-3 backdrop-blur">
          <div className="panel mx-auto flex h-full w-full max-w-[1700px] flex-col p-3">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h3 className="font-[var(--font-display)] text-xl font-semibold text-slate-100">Full Preview</h3>
              <button type="button" className="ghost-btn" onClick={() => setPreviewFullscreen(false)}>
                Close
              </button>
            </div>
            <div className="overflow-hidden rounded-xl border border-white/20 bg-slate-950/50">
              <iframe
                title="ZoSwi Instant Builder Full Preview"
                srcDoc={previewHtml}
                className="h-[calc(100vh-120px)] w-full border-0"
                sandbox="allow-scripts allow-same-origin allow-forms"
              />
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
