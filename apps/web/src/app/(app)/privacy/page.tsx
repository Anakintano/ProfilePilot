"use client";

import { useState } from "react";
import { Header } from "@/components/Header";
import { SectionCard } from "@/components/SectionCard";
import * as api from "@/lib/api";
import { getApiErrorDetail } from "@/lib/errors";

type DeleteState = "idle" | "confirming" | "deleting" | "done" | "error";

export default function PrivacyPage() {
  const [state, setState] = useState<DeleteState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [deletedCounts, setDeletedCounts] = useState<Record<string, number> | null>(null);

  async function confirmDelete() {
    setState("deleting");
    setError(null);
    try {
      const result = await api.deleteMyData();
      setDeletedCounts(result.deleted);
      setState("done");
    } catch (err) {
      setError(getApiErrorDetail(err));
      setState("error");
    }
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="font-serif text-2xl text-ink">Privacy and your data</h1>

        <div className="mt-6 space-y-4">
          <SectionCard title="Raw uploads are deleted automatically">
            <p className="text-sm leading-relaxed text-ink/75">
              The résumé, LinkedIn export, or screenshots you upload are stored only long enough
              to extract the information needed for your report. Raw files are automatically and
              permanently deleted 24 hours after upload, whether or not you finish the analysis.
            </p>
          </SectionCard>

          <SectionCard title="What we keep after that">
            <p className="text-sm leading-relaxed text-ink/75">
              The extracted fields, scores, recommendations, and any feedback you give are kept so
              you can return to your report. They contain the text you confirmed during extraction
              review, not the original file.
            </p>
          </SectionCard>

          <SectionCard title="Delete everything now">
            <p className="text-sm leading-relaxed text-ink/75">
              You can permanently delete your uploads, analyses, goal profiles, and their extracted
              data immediately, without waiting for the 24-hour window. This can&apos;t be undone.
            </p>

            {state === "idle" && (
              <button
                type="button"
                onClick={() => setState("confirming")}
                className="focus-ring mt-4 rounded border border-red/50 px-4 py-2 text-sm font-medium text-red hover:bg-red/5"
              >
                Delete my data
              </button>
            )}

            {state === "confirming" && (
              <div className="mt-4 rounded-md border border-red/40 bg-red/5 p-4">
                <p className="text-sm font-medium text-ink">
                  This permanently deletes all your uploads, analyses, extracted fields, and
                  feedback. This cannot be undone.
                </p>
                <div className="mt-3 flex gap-3">
                  <button
                    type="button"
                    onClick={confirmDelete}
                    className="focus-ring rounded border border-red bg-red px-4 py-2 text-sm font-medium text-cream hover:opacity-90"
                  >
                    Yes, delete everything
                  </button>
                  <button
                    type="button"
                    onClick={() => setState("idle")}
                    className="focus-ring rounded border border-ink/20 px-4 py-2 text-sm text-ink/70 hover:border-ink/40"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {state === "deleting" && <p className="mt-4 text-sm text-ink/60">Deleting…</p>}

            {state === "done" && deletedCounts && (
              <div className="mt-4 rounded-md border border-teal/40 bg-teal/5 p-4 text-sm text-ink/80">
                <p className="font-medium text-ink">Your data has been deleted.</p>
                <ul className="mt-2 space-y-0.5 text-xs text-ink/60">
                  {Object.entries(deletedCounts).map(([key, count]) => (
                    <li key={key}>
                      {key.replace(/_/g, " ")}: {count}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {state === "error" && error && (
              <div className="mt-4 rounded-md border border-red/40 bg-red/5 p-4">
                <p className="text-sm text-red">{error}</p>
                <button
                  type="button"
                  onClick={() => setState("confirming")}
                  className="focus-ring mt-3 rounded border border-ink/25 px-4 py-2 text-sm text-ink hover:border-teal hover:text-teal"
                >
                  Try again
                </button>
              </div>
            )}
          </SectionCard>
        </div>
      </main>
    </div>
  );
}
