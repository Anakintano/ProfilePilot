"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Header } from "@/components/Header";
import { VerticalTimeline, type TimelineStep } from "@/components/VerticalTimeline";
import * as api from "@/lib/api";
import { getApiErrorDetail } from "@/lib/errors";
import { WORKFLOW_STAGES } from "@contracts/index";
import type { AnalysisEventOut, AnalysisOut, Stage } from "@contracts/types";

const STAGE_LABELS: Record<Stage, string> = {
  ingest: "Ingest",
  extract: "Extract",
  normalize: "Normalize",
  score: "Score",
  recommend: "Recommend",
  audit: "Audit",
  publish: "Publish",
};

const STAGE_DESCRIPTIONS: Record<Stage, string> = {
  ingest: "Reading your uploaded files.",
  extract: "Pulling structured fields out of the document.",
  normalize: "Cleaning and standardizing extracted text.",
  score: "Scoring your profile against the target role.",
  recommend: "Drafting evidence-backed rewrite suggestions.",
  audit: "Checking every suggestion against your original document.",
  publish: "Assembling the final report.",
};

function buildTimelineSteps(currentStage: Stage, events: AnalysisEventOut[]): TimelineStep[] {
  const currentIndex = WORKFLOW_STAGES.indexOf(currentStage);
  return WORKFLOW_STAGES.map((stage, index) => {
    const latestEventForStage = events.filter((e) => e.stage === stage).at(-1);
    const status = index < currentIndex ? "done" : index === currentIndex ? "current" : "pending";
    return {
      label: STAGE_LABELS[stage],
      description: latestEventForStage?.message ?? STAGE_DESCRIPTIONS[stage],
      status,
      timestamp: latestEventForStage
        ? new Date(latestEventForStage.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })
        : undefined,
    };
  });
}

function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export default function ProcessingPage() {
  const params = useParams<{ id: string }>();
  const analysisId = params.id;
  const router = useRouter();

  const [analysis, setAnalysis] = useState<AnalysisOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [events, setEvents] = useState<AnalysisEventOut[]>([]);
  const [currentStage, setCurrentStage] = useState<Stage>("ingest");
  const [failure, setFailure] = useState<{ code: string | null; message: string | null } | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const startedAtRef = useRef<number | null>(null);
  const routedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getAnalysis(analysisId)
      .then((data) => {
        if (cancelled) return;
        setAnalysis(data);
        setCurrentStage(data.current_stage);
        startedAtRef.current = new Date(data.created_at).getTime();
        if (data.status === "completed") {
          routedRef.current = true;
          router.replace(`/analyses/${analysisId}/report`);
        } else if (data.status === "needs_review") {
          routedRef.current = true;
          router.replace(`/analyses/${analysisId}/extraction`);
        } else if (data.status === "failed") {
          setFailure({ code: data.error_code, message: data.error_message });
        }
      })
      .catch((err) => {
        if (!cancelled) setLoadError(getApiErrorDetail(err));
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId, router]);

  useEffect(() => {
    if (routedRef.current || failure) return;
    const source = new EventSource(api.eventsUrl(analysisId));

    source.onmessage = (event) => {
      let payload: AnalysisEventOut;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      setEvents((prev) => [...prev, payload]);
      setCurrentStage(payload.stage);

      if (payload.status === "completed") {
        routedRef.current = true;
        source.close();
        router.push(`/analyses/${analysisId}/report`);
      } else if (payload.status === "needs_review") {
        routedRef.current = true;
        source.close();
        router.push(`/analyses/${analysisId}/extraction`);
      } else if (payload.status === "failed") {
        source.close();
        api
          .getAnalysis(analysisId)
          .then((data) => setFailure({ code: data.error_code, message: data.error_message }))
          .catch(() => setFailure({ code: null, message: "The analysis failed and details couldn't be loaded." }));
      }
    };

    return () => {
      source.close();
    };
  }, [analysisId, router, failure]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (startedAtRef.current) setElapsedMs(Date.now() - startedAtRef.current);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const latestMessage = events.at(-1)?.message ?? "Waiting for the first update…";

  if (loadError) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="mx-auto max-w-3xl px-6 py-14">
          <div className="rounded-md border border-red/40 bg-red/5 p-5">
            <h1 className="font-serif text-xl text-ink">Couldn&apos;t load this analysis</h1>
            <p className="mt-2 text-sm text-ink/70">{loadError}</p>
            <Link
              href="/upload"
              className="focus-ring mt-4 inline-block rounded border border-ink/25 px-4 py-2 text-sm text-ink hover:border-teal hover:text-teal"
            >
              Back to upload
            </Link>
          </div>
        </main>
      </div>
    );
  }

  if (failure) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="mx-auto max-w-3xl px-6 py-14">
          <div className="rounded-md border border-red/40 bg-red/5 p-5">
            <h1 className="font-serif text-xl text-ink">This analysis failed</h1>
            <p className="mt-2 text-sm text-ink/70">
              {failure.message ?? "The processing pipeline hit an error and couldn't finish."}
            </p>
            {failure.code ? <p className="mt-1 text-xs text-ink/40">Error code: {failure.code}</p> : null}
            <Link
              href="/upload"
              className="focus-ring mt-4 inline-block rounded border border-ink/25 px-4 py-2 text-sm text-ink hover:border-teal hover:text-teal"
            >
              Back to upload
            </Link>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-3xl px-6 py-14">
        <h1 className="font-serif text-2xl text-ink">Processing your analysis</h1>
        <p className="mt-2 text-sm text-ink/60">
          Running for {formatElapsed(elapsedMs)} · this usually takes a couple of minutes.
        </p>

        <div className="mt-8">
          <VerticalTimeline steps={buildTimelineSteps(currentStage, events)} />
        </div>

        <div aria-live="polite" className="mt-8 rounded-md border border-ink/10 p-4">
          <p className="text-sm text-ink/80">{latestMessage}</p>
        </div>

        {events.length > 0 ? (
          <ul className="mt-6 space-y-2 text-xs text-ink/50">
            {events
              .slice()
              .reverse()
              .map((e) => (
                <li key={e.seq} className="border-b border-ink/5 pb-2">
                  <span className="font-medium text-ink/70">{e.stage}</span> — {e.message}
                </li>
              ))}
          </ul>
        ) : null}

        {analysis?.status === "queued" ? (
          <p className="mt-6 text-xs text-ink/40">Queued — waiting for a worker to pick this up.</p>
        ) : null}
      </main>
    </div>
  );
}
