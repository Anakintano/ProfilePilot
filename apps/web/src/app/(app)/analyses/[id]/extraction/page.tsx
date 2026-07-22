"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Header } from "@/components/Header";
import { SectionCard } from "@/components/SectionCard";
import { ConfidenceTag } from "@/components/ConfidenceTag";
import * as api from "@/lib/api";
import { getApiErrorDetail } from "@/lib/errors";
import type { ExtractedField, ExtractionOut } from "@contracts/types";

function baselineValue(field: ExtractedField): string {
  return field.corrected_value ?? field.value;
}

export default function ExtractionReviewPage() {
  const params = useParams<{ id: string }>();
  const analysisId = params.id;
  const router = useRouter();

  const [extraction, setExtraction] = useState<ExtractionOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  function load() {
    setLoadError(null);
    setExtraction(null);
    api
      .getExtraction(analysisId)
      .then(setExtraction)
      .catch((err) => setLoadError(getApiErrorDetail(err)));
  }

  useEffect(load, [analysisId]);

  const grouped = useMemo(() => {
    if (!extraction) return new Map<string, ExtractedField[]>();
    const map = new Map<string, ExtractedField[]>();
    for (const field of extraction.fields) {
      const list = map.get(field.section) ?? [];
      list.push(field);
      map.set(field.section, list);
    }
    return map;
  }, [extraction]);

  async function handleSubmit() {
    if (!extraction) return;
    setSubmitting(true);
    setSubmitError(null);
    const corrections = extraction.fields
      .filter((f) => f.id in edits && edits[f.id] !== baselineValue(f))
      .map((f) => ({ field_id: f.id, corrected_value: edits[f.id] }));
    try {
      await api.patchExtraction(analysisId, corrections);
      router.push(`/analyses/${analysisId}/processing`);
    } catch (err) {
      setSubmitError(getApiErrorDetail(err));
      setSubmitting(false);
    }
  }

  if (loadError) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="mx-auto max-w-3xl px-6 py-14">
          <div className="rounded-md border border-red/40 bg-red/5 p-5">
            <h1 className="font-serif text-xl text-ink">Couldn&apos;t load the extraction</h1>
            <p className="mt-2 text-sm text-ink/70">{loadError}</p>
            <button
              type="button"
              onClick={load}
              className="focus-ring mt-4 rounded border border-ink/25 px-4 py-2 text-sm text-ink hover:border-teal hover:text-teal"
            >
              Retry
            </button>
          </div>
        </main>
      </div>
    );
  }

  if (!extraction) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="mx-auto max-w-3xl px-6 py-14">
          <p className="text-sm text-ink/60">Loading extracted fields…</p>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="font-serif text-2xl text-ink">Review what we found</h1>
        <p className="mt-2 text-sm text-ink/70">
          Confirm the fields we extracted before scoring runs. Fix anything that&apos;s wrong or
          incomplete — corrections feed directly into your score and rewrite suggestions.
        </p>

        {extraction.required_sections_missing.length > 0 ? (
          <div className="mt-6 rounded-md border border-amber/50 bg-amber/5 p-4">
            <h2 className="font-serif text-lg text-ink">We couldn&apos;t confidently find:</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink/80">
              {extraction.required_sections_missing.map((section) => (
                <li key={section} className="capitalize">
                  {section} — please check your file, or note this section is genuinely absent.
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {extraction.fields.length === 0 ? (
          <p className="mt-8 text-sm text-ink/60">
            No fields were extracted from your upload. Go back and try a clearer file, or continue
            to see what scoring makes of an empty profile.
          </p>
        ) : (
          <div className="mt-8 space-y-6">
            {Array.from(grouped.entries()).map(([section, fields]) => (
              <SectionCard key={section} title={section} headingLevel="h2">
                <ul className="space-y-4">
                  {fields.map((field) => (
                    <li key={field.id} className="border-t border-ink/5 pt-3 first:border-t-0 first:pt-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-xs font-medium uppercase tracking-wide text-ink/50">
                          {field.field_key.replace(/_/g, " ")}
                        </span>
                        <ConfidenceTag confidence={field.confidence} />
                      </div>
                      <textarea
                        value={edits[field.id] ?? baselineValue(field)}
                        onChange={(e) => setEdits((prev) => ({ ...prev, [field.id]: e.target.value }))}
                        rows={Math.min(4, Math.max(1, Math.ceil(baselineValue(field).length / 80)))}
                        className="focus-ring mt-2 w-full rounded border border-ink/20 bg-cream px-3 py-2 text-sm text-ink"
                      />
                      {field.user_corrected ? (
                        <p className="mt-1 text-xs text-teal">Previously corrected</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </SectionCard>
            ))}
          </div>
        )}

        {submitError ? <p className="mt-4 text-sm text-red">{submitError}</p> : null}

        <div className="mt-8 flex items-center justify-between">
          <Link
            href="/upload"
            className="focus-ring rounded border border-ink/20 px-4 py-2 text-sm text-ink/70 hover:border-ink/40"
          >
            Back to upload
          </Link>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="focus-ring rounded border border-teal bg-teal px-6 py-3 text-sm font-medium text-cream disabled:opacity-60"
          >
            {submitting ? "Saving…" : "Looks good, continue"}
          </button>
        </div>
      </main>
    </div>
  );
}
