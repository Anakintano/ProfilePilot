"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Header } from "@/components/Header";
import { SectionCard } from "@/components/SectionCard";
import { ConfidenceTag } from "@/components/ConfidenceTag";
import { AuditStatusBadge } from "@/components/AuditStatusBadge";
import { ImpactEffortBadge } from "@/components/ImpactEffortBadge";
import * as api from "@/lib/api";
import { getApiErrorDetail } from "@/lib/errors";
import type { AnalysisOut, ConfidenceBand } from "@contracts/types";

const BAND_STYLES: Record<ConfidenceBand, { label: string; className: string }> = {
  low: { label: "Low confidence", className: "border-red/40 text-red" },
  medium: { label: "Medium confidence", className: "border-amber/50 text-amber" },
  high: { label: "High confidence", className: "border-teal/40 text-teal" },
};

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const analysisId = params.id;
  const router = useRouter();

  const [analysis, setAnalysis] = useState<AnalysisOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  function load() {
    setLoadError(null);
    api
      .getAnalysis(analysisId)
      .then((data) => {
        setAnalysis(data);
        if (!data.report) {
          router.replace(`/analyses/${analysisId}/processing`);
        }
      })
      .catch((err) => setLoadError(getApiErrorDetail(err)));
  }

  useEffect(load, [analysisId, router]);

  if (loadError) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="mx-auto max-w-3xl px-6 py-14">
          <div className="rounded-md border border-red/40 bg-red/5 p-5">
            <h1 className="font-serif text-xl text-ink">Couldn&apos;t load the report</h1>
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

  if (!analysis || !analysis.report) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="mx-auto max-w-3xl px-6 py-14">
          <p className="text-sm text-ink/60">Loading report…</p>
        </main>
      </div>
    );
  }

  const report = analysis.report;
  const band = BAND_STYLES[report.confidence_band];
  const formattedScore = Number.isInteger(report.total_score)
    ? report.total_score.toString()
    : report.total_score.toFixed(1);
  const sortedRecommendations = [...report.recommendations].sort((a, b) => a.priority - b.priority);

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-3xl px-6 py-10">
        <p className="text-xs uppercase tracking-wide text-ink/50">Report</p>
        <h1 className="mt-1 font-serif text-2xl text-ink">Your profile diagnostic</h1>

        <div className="mt-8 flex flex-wrap items-end justify-between gap-4 border-b border-ink/10 pb-6">
          <div>
            <p className="text-xs uppercase tracking-wide text-ink/50">Overall score</p>
            <p className="font-serif text-5xl leading-none text-ink">{formattedScore}</p>
          </div>
          <span className={`rounded-sm border px-3 py-1 text-sm font-medium ${band.className}`}>
            {band.label}
          </span>
        </div>

        <section className="mt-8">
          <h2 className="font-serif text-xl text-ink">Score by dimension</h2>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-ink/15 text-left text-xs uppercase tracking-wide text-ink/50">
                  <th className="py-2 pr-3 font-medium">Dimension</th>
                  <th className="py-2 pr-3 font-medium">Score</th>
                  <th className="py-2 pr-3 font-medium">Confidence</th>
                  <th className="py-2 font-medium">Reasoning</th>
                </tr>
              </thead>
              <tbody>
                {report.dimension_scores.map((item) => (
                  <tr key={item.dimension} className="border-b border-ink/5 align-top">
                    <td className="py-3 pr-3 font-medium capitalize text-ink">
                      {item.dimension.replace(/_/g, " ")}
                    </td>
                    <td className="py-3 pr-3 tabular-nums text-ink">{item.score.toFixed(1)}</td>
                    <td className="py-3 pr-3">
                      <ConfidenceTag confidence={item.confidence} />
                    </td>
                    <td className="max-w-sm py-3">
                      <p className="text-ink/80">{item.reasoning_summary}</p>
                      {item.evidence_refs.length > 0 || item.improvement_conditions.length > 0 ? (
                        <details className="mt-1">
                          <summary className="focus-ring cursor-pointer rounded-sm text-xs text-teal">
                            Evidence &amp; conditions
                          </summary>
                          <div className="mt-2 space-y-2 text-xs text-ink/70">
                            {item.evidence_refs.length > 0 ? (
                              <div>
                                <p className="font-medium text-ink/50">Evidence</p>
                                <ul className="list-disc pl-4">
                                  {item.evidence_refs.map((ref, i) => (
                                    <li key={i}>{ref}</li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                            {item.improvement_conditions.length > 0 ? (
                              <div>
                                <p className="font-medium text-ink/50">To improve this score</p>
                                <ul className="list-disc pl-4">
                                  {item.improvement_conditions.map((c, i) => (
                                    <li key={i}>{c}</li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                          </div>
                        </details>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div className="mt-8">
          <SectionCard title="Limitations">
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink/70">
              {report.limitations.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          </SectionCard>
        </div>

        <section className="mt-10">
          <h2 className="font-serif text-xl text-ink">Recommendations</h2>
          <ol className="mt-4 space-y-6">
            {sortedRecommendations.map((rec) => (
              <li key={rec.id} className="rounded-md border border-ink/10 p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-ink/50">
                    Priority {rec.priority} · {rec.source_section}
                  </span>
                  <AuditStatusBadge status={rec.audit_status} />
                </div>
                {rec.original_text ? (
                  <p className="mt-3 text-sm text-ink/50 line-through decoration-ink/20">
                    {rec.original_text}
                  </p>
                ) : null}
                <p className="mt-2 text-sm text-ink">{rec.proposed_rewrite}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <ImpactEffortBadge label="Impact" value={rec.expected_impact} />
                  <ImpactEffortBadge label="Effort" value={rec.effort} />
                </div>
                {rec.audit_notes ? (
                  <details className="mt-2">
                    <summary className="focus-ring cursor-pointer rounded-sm text-xs text-teal">
                      Audit notes
                    </summary>
                    <p className="mt-1 text-xs text-ink/70">{rec.audit_notes}</p>
                  </details>
                ) : null}
                {rec.research_citations.length > 0 ? (
                  <details className="mt-2">
                    <summary className="focus-ring cursor-pointer rounded-sm text-xs text-teal">
                      Research citations ({rec.research_citations.length})
                    </summary>
                    <ul className="mt-1 list-disc pl-4 text-xs text-ink/70">
                      {rec.research_citations.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
                <RecommendationFeedback analysisId={analysisId} recommendationId={rec.id} />
              </li>
            ))}
          </ol>
        </section>

        <div className="mt-10 mb-16">
          <SectionCard title="Your prioritized next steps">
            <ol className="list-decimal space-y-2 pl-5 text-sm text-ink/80">
              {report.action_plan.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          </SectionCard>
        </div>
      </main>
    </div>
  );
}

function RecommendationFeedback({
  analysisId,
  recommendationId,
}: {
  analysisId: string;
  recommendationId: string;
}) {
  const [reason, setReason] = useState("");
  const [usefulness, setUsefulness] = useState<number | null>(null);
  const [status, setStatus] = useState<"idle" | "submitting" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit(accepted: boolean) {
    setStatus("submitting");
    setError(null);
    try {
      await api.submitFeedback(analysisId, {
        recommendation_id: recommendationId,
        accepted,
        rejection_reason: accepted ? null : reason.trim() || null,
        usefulness_score: usefulness,
      });
      setStatus("done");
    } catch (err) {
      setStatus("error");
      setError(getApiErrorDetail(err));
    }
  }

  if (status === "done") {
    return <p className="mt-3 border-t border-ink/5 pt-3 text-xs text-teal">Feedback recorded — thank you.</p>;
  }

  return (
    <div className="mt-3 border-t border-ink/5 pt-3">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => submit(true)}
          disabled={status === "submitting"}
          className="focus-ring rounded-sm border border-teal px-3 py-1 text-xs font-medium text-teal hover:bg-teal/10 disabled:opacity-50"
        >
          Accept
        </button>
        <button
          type="button"
          onClick={() => submit(false)}
          disabled={status === "submitting"}
          className="focus-ring rounded-sm border border-red/50 px-3 py-1 text-xs font-medium text-red hover:bg-red/10 disabled:opacity-50"
        >
          Reject
        </button>
        <fieldset className="flex items-center gap-1 border-0 p-0 text-xs text-ink/50">
          <legend className="sr-only">Usefulness score</legend>
          Useful:
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={usefulness === n}
              onClick={() => setUsefulness(n)}
              className={`focus-ring h-5 w-5 rounded-sm border text-center leading-5 ${
                usefulness === n ? "border-teal bg-teal text-cream" : "border-ink/20 text-ink/60"
              }`}
            >
              {n}
            </button>
          ))}
        </fieldset>
      </div>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Optional reason (used if you reject)"
        rows={2}
        className="focus-ring mt-2 w-full rounded border border-ink/15 bg-cream px-2 py-1 text-xs text-ink"
      />
      {status === "error" && error ? <p className="mt-1 text-xs text-red">{error}</p> : null}
    </div>
  );
}
