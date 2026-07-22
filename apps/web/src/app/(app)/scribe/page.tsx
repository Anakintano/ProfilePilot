"use client";

import { useState } from "react";
import Image from "next/image";
import { Header } from "@/components/Header";
import { SectionCard } from "@/components/SectionCard";
import * as api from "@/lib/api";
import { getApiErrorDetail, isApiErrorStatus } from "@/lib/errors";
import type { ScribeCommentType, ScribeStyle } from "@contracts/types";

type Tab = "post" | "comment";

const STYLE_OPTIONS: { value: ScribeStyle; label: string; hint: string }[] = [
  { value: "professional", label: "Professional", hint: "Formal, workplace-appropriate tone" },
  { value: "storytelling", label: "Storytelling", hint: "Narrative hook, turning point, takeaway" },
  { value: "thought_leadership", label: "Thought leadership", hint: "Confident point of view on a trend" },
  { value: "casual", label: "Casual", hint: "Conversational, friendly tone" },
  { value: "data_driven", label: "Data-driven", hint: "Leads with a number or stat" },
  { value: "listicle", label: "Listicle", hint: "Numbered list format" },
];

const COMMENT_TYPE_OPTIONS: { value: ScribeCommentType; label: string; hint: string }[] = [
  { value: "engaging", label: "Engaging", hint: "Adds value, sparks discussion" },
  { value: "supportive", label: "Supportive", hint: "Warm and encouraging" },
  { value: "insightful", label: "Insightful", hint: "Adds a non-obvious angle" },
  { value: "question", label: "Question", hint: "Asks a genuine follow-up" },
  { value: "congratulatory", label: "Congratulatory", hint: "Celebrates an achievement" },
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // clipboard permission denied or unavailable -- nothing further we can do here
        }
      }}
      className="focus-ring rounded border border-ink/25 px-3 py-1.5 text-xs font-medium text-ink hover:border-teal hover:text-teal"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

export default function ScribePage() {
  const [tab, setTab] = useState<Tab>("post");

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="relative mb-8 h-28 overflow-hidden rounded-md border border-ink/10 sm:h-36">
          <Image
            src="/images/scribe-writing.jpg"
            alt="Hands typing on a laptop keyboard"
            fill
            sizes="768px"
            className="object-cover"
          />
        </div>

        <h1 className="font-serif text-2xl text-ink">Scribe</h1>
        <p className="mt-2 text-sm text-ink/70">
          Draft a LinkedIn post or a reply comment. Nothing here is saved — generate, copy, and
          paste it wherever you need it.
        </p>

        <div role="tablist" aria-label="Scribe mode" className="mt-6 flex gap-2 border-b border-ink/10">
          {(
            [
              { key: "post" as const, label: "Post Writer" },
              { key: "comment" as const, label: "Comment Generator" },
            ]
          ).map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
              className={`focus-ring -mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                tab === t.key
                  ? "border-teal text-teal"
                  : "border-transparent text-ink/60 hover:text-ink"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="mt-6">
          {tab === "post" ? <PostWriter /> : <CommentGenerator />}
        </div>
      </main>
    </div>
  );
}

function PostWriter() {
  const [style, setStyle] = useState<ScribeStyle>("professional");
  const [topic, setTopic] = useState("");
  const [roughSketch, setRoughSketch] = useState("");
  const [useWebSearch, setUseWebSearch] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ post_text: string; hashtags: string[] } | null>(null);

  const canGenerate = topic.trim().length >= 2 && !loading;

  async function handleGenerate() {
    if (!canGenerate) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.generateScribePost({
        style,
        topic: topic.trim(),
        rough_sketch: roughSketch.trim() ? roughSketch.trim() : null,
        use_web_search: useWebSearch,
      });
      setResult(res);
    } catch (err) {
      const detail = getApiErrorDetail(err);
      setError(isApiErrorStatus(err, 429) ? `Rate limited: ${detail}` : detail);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionCard title="Post details">
        <div>
          <p className="text-sm font-medium text-ink">Style</p>
          <div role="radiogroup" aria-label="Post style" className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {STYLE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={style === opt.value}
                onClick={() => setStyle(opt.value)}
                className={`focus-ring rounded border px-4 py-3 text-left transition-colors ${
                  style === opt.value ? "border-teal bg-teal/10" : "border-ink/20 hover:border-ink/40"
                }`}
              >
                <span className="block font-medium text-ink">{opt.label}</span>
                <span className="block text-xs text-ink/60">{opt.hint}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5">
          <label htmlFor="scribe-topic" className="text-sm font-medium text-ink">
            Topic
          </label>
          <input
            id="scribe-topic"
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="E.g. &quot;wrapping up my summer internship&quot;"
            className="focus-ring mt-2 w-full rounded border border-ink/20 bg-cream px-3 py-2 text-ink"
          />
        </div>

        <div className="mt-5">
          <label htmlFor="scribe-sketch" className="text-sm font-medium text-ink">
            Rough sketch or draft{" "}
            <span className="font-normal text-ink/50">(optional)</span>
          </label>
          <textarea
            id="scribe-sketch"
            value={roughSketch}
            onChange={(e) => setRoughSketch(e.target.value)}
            rows={4}
            placeholder="Paste any rough notes or a draft you want polished — leave blank to write from scratch"
            className="focus-ring mt-2 w-full rounded border border-ink/20 bg-cream px-3 py-2 text-ink"
          />
        </div>

        <label className="mt-5 flex items-start gap-2.5 text-sm text-ink/80">
          <input
            type="checkbox"
            checked={useWebSearch}
            onChange={(e) => setUseWebSearch(e.target.checked)}
            className="focus-ring mt-0.5 h-4 w-4 rounded border-ink/30"
          />
          <span>
            Ground with a live web search
            <span className="block text-xs text-ink/50">
              Looks up your topic and folds relevant background into the draft — never presented as
              your own personal claims.
            </span>
          </span>
        </label>

        {error ? <p className="mt-4 text-sm text-red">{error}</p> : null}

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={handleGenerate}
            disabled={!canGenerate}
            className="focus-ring rounded border border-teal bg-teal px-5 py-2 text-sm font-medium text-cream disabled:cursor-not-allowed disabled:border-ink/15 disabled:bg-ink/10 disabled:text-ink/40"
          >
            {loading ? "Generating…" : "Generate post"}
          </button>
        </div>
      </SectionCard>

      {result ? (
        <SectionCard title="Generated post" action={<CopyButton text={formatPostForCopy(result)} />}>
          <p className="whitespace-pre-wrap text-sm text-ink">{result.post_text}</p>
          {result.hashtags.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {result.hashtags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-sm border border-teal/30 bg-teal/5 px-2.5 py-1 text-xs text-teal"
                >
                  #{tag}
                </span>
              ))}
            </div>
          ) : null}
        </SectionCard>
      ) : null}
    </div>
  );
}

function formatPostForCopy(result: { post_text: string; hashtags: string[] }): string {
  if (result.hashtags.length === 0) return result.post_text;
  return `${result.post_text}\n\n${result.hashtags.map((t) => `#${t}`).join(" ")}`;
}

function CommentGenerator() {
  const [postContent, setPostContent] = useState("");
  const [commentType, setCommentType] = useState<ScribeCommentType>("engaging");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ comment_text: string } | null>(null);

  const canGenerate = postContent.trim().length >= 2 && !loading;

  async function handleGenerate() {
    if (!canGenerate) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.generateScribeComment({
        post_content: postContent.trim(),
        comment_type: commentType,
      });
      setResult(res);
    } catch (err) {
      const detail = getApiErrorDetail(err);
      setError(isApiErrorStatus(err, 429) ? `Rate limited: ${detail}` : detail);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionCard title="Post to reply to">
        <label htmlFor="scribe-post-content" className="text-sm font-medium text-ink">
          Paste the post text
        </label>
        <textarea
          id="scribe-post-content"
          value={postContent}
          onChange={(e) => setPostContent(e.target.value)}
          rows={6}
          placeholder="Paste the LinkedIn post you want to comment on"
          className="focus-ring mt-2 w-full rounded border border-ink/20 bg-cream px-3 py-2 text-ink"
        />

        <div className="mt-5">
          <p className="text-sm font-medium text-ink">Comment type</p>
          <div role="radiogroup" aria-label="Comment type" className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {COMMENT_TYPE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={commentType === opt.value}
                onClick={() => setCommentType(opt.value)}
                className={`focus-ring rounded border px-4 py-3 text-left transition-colors ${
                  commentType === opt.value ? "border-teal bg-teal/10" : "border-ink/20 hover:border-ink/40"
                }`}
              >
                <span className="block font-medium text-ink">{opt.label}</span>
                <span className="block text-xs text-ink/60">{opt.hint}</span>
              </button>
            ))}
          </div>
        </div>

        {error ? <p className="mt-4 text-sm text-red">{error}</p> : null}

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={handleGenerate}
            disabled={!canGenerate}
            className="focus-ring rounded border border-teal bg-teal px-5 py-2 text-sm font-medium text-cream disabled:cursor-not-allowed disabled:border-ink/15 disabled:bg-ink/10 disabled:text-ink/40"
          >
            {loading ? "Generating…" : "Generate comment"}
          </button>
        </div>
      </SectionCard>

      {result ? (
        <SectionCard title="Generated comment" action={<CopyButton text={result.comment_text} />}>
          <p className="whitespace-pre-wrap text-sm text-ink">{result.comment_text}</p>
        </SectionCard>
      ) : null}
    </div>
  );
}
