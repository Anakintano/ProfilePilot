"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { Header } from "@/components/Header";
import {
  clearIntakeDraft,
  loadIntakeDraft,
  saveGoalProfile,
  saveIntakeDraft,
} from "@/lib/goalProfile";
import type { GoalProfile, Seniority } from "@contracts/types";

const STEPS = ["target_role", "seniority", "geography", "outcome", "job_description"] as const;
type StepKey = (typeof STEPS)[number];

const SENIORITY_OPTIONS: { value: Seniority; label: string; hint: string }[] = [
  { value: "intern", label: "Intern", hint: "Targeting an internship" },
  { value: "entry", label: "Entry-level", hint: "0–1 years, first full-time role" },
  { value: "junior", label: "Junior", hint: "1–3 years experience" },
];

interface DraftState {
  target_role: string;
  seniority: Seniority | "";
  geography: string;
  outcome: string;
  job_description: string;
}

const EMPTY_DRAFT: DraftState = {
  target_role: "",
  seniority: "",
  geography: "",
  outcome: "",
  job_description: "",
};

export default function IntakePage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [hydrated, setHydrated] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const saved = loadIntakeDraft();
    if (saved) {
      setDraft({
        target_role: saved.target_role ?? "",
        seniority: (saved.seniority as Seniority) ?? "",
        geography: saved.geography ?? "",
        outcome: saved.outcome ?? "",
        job_description: saved.job_description ?? "",
      });
      if (typeof saved.step === "number") {
        setStep(Math.min(Math.max(saved.step, 0), STEPS.length - 1));
      }
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    saveIntakeDraft({ ...draft, step });
  }, [draft, step, hydrated]);

  const currentKey: StepKey = STEPS[step];

  function update<K extends keyof DraftState>(key: K, value: DraftState[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
    setError(null);
  }

  function validateStep(key: StepKey): string | null {
    if (key === "target_role" && draft.target_role.trim().length < 2) {
      return "Enter the role you're targeting (at least 2 characters).";
    }
    if (key === "seniority" && !draft.seniority) {
      return "Choose the seniority level closest to what you're applying for.";
    }
    if (key === "geography" && draft.geography.trim().length < 2) {
      return 'Enter a location or "Remote".';
    }
    if (key === "outcome" && draft.outcome.trim().length < 2) {
      return "Describe the outcome you want.";
    }
    return null;
  }

  function goNext() {
    const err = validateStep(currentKey);
    if (err) {
      setError(err);
      return;
    }
    if (step < STEPS.length - 1) {
      setStep((s) => s + 1);
      return;
    }
    finish();
  }

  function goBack() {
    setError(null);
    setStep((s) => Math.max(0, s - 1));
  }

  function finish() {
    const profile: GoalProfile = {
      target_role: draft.target_role.trim(),
      seniority: draft.seniority as Seniority,
      geography: draft.geography.trim(),
      outcome: draft.outcome.trim(),
      job_description: draft.job_description.trim() ? draft.job_description.trim() : null,
    };
    saveGoalProfile(profile);
    clearIntakeDraft();
    router.push("/upload");
  }

  if (!hydrated) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="mx-auto max-w-3xl px-6 py-14">
          <p className="text-sm text-ink/60">Loading…</p>
        </main>
      </div>
    );
  }

  const answered: { label: string; value: string }[] = [];
  if (draft.target_role) answered.push({ label: "Target role", value: draft.target_role });
  if (draft.seniority) {
    answered.push({
      label: "Seniority",
      value: SENIORITY_OPTIONS.find((o) => o.value === draft.seniority)?.label ?? draft.seniority,
    });
  }
  if (draft.geography) answered.push({ label: "Geography", value: draft.geography });
  if (draft.outcome) answered.push({ label: "Outcome", value: draft.outcome });
  if (draft.job_description) answered.push({ label: "Job description", value: "Added" });

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="relative mb-8 h-28 overflow-hidden rounded-md border border-ink/10 sm:h-36">
          <Image
            src="/images/intake-goals.jpg"
            alt="A planner open to a monthly goals page"
            fill
            sizes="768px"
            className="object-cover"
          />
        </div>

        <p className="text-sm text-ink/60">
          Step {step + 1} of {STEPS.length}
        </p>

        {answered.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2 border-b border-ink/10 pb-6">
            {answered.map((a) => (
              <span
                key={a.label}
                className="rounded-sm border border-ink/15 bg-ink/[0.03] px-2.5 py-1 text-xs text-ink/70"
              >
                <span className="text-ink/45">{a.label}:</span> {a.value}
              </span>
            ))}
          </div>
        ) : null}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            goNext();
          }}
          className="mt-8"
        >
          {currentKey === "target_role" && (
            <div>
              <h1 className="font-serif text-2xl text-ink">What role are you targeting?</h1>
              <p className="mt-1 text-sm text-ink/60">
                E.g. &quot;Data analyst intern&quot; or &quot;Frontend software engineer&quot;.
              </p>
              <input
                autoFocus
                type="text"
                value={draft.target_role}
                onChange={(e) => update("target_role", e.target.value)}
                className="focus-ring mt-4 w-full rounded border border-ink/20 bg-cream px-3 py-2 text-ink"
                placeholder="Target role"
              />
            </div>
          )}

          {currentKey === "seniority" && (
            <div>
              <h1 className="font-serif text-2xl text-ink">What level are you applying at?</h1>
              <div
                role="radiogroup"
                aria-label="Seniority"
                className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3"
              >
                {SENIORITY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={draft.seniority === opt.value}
                    onClick={() => update("seniority", opt.value)}
                    className={`focus-ring rounded border px-4 py-3 text-left transition-colors ${
                      draft.seniority === opt.value
                        ? "border-teal bg-teal/10"
                        : "border-ink/20 hover:border-ink/40"
                    }`}
                  >
                    <span className="block font-medium text-ink">{opt.label}</span>
                    <span className="block text-xs text-ink/60">{opt.hint}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {currentKey === "geography" && (
            <div>
              <h1 className="font-serif text-2xl text-ink">Where are you looking?</h1>
              <p className="mt-1 text-sm text-ink/60">City, country, or &quot;Remote&quot;.</p>
              <input
                autoFocus
                type="text"
                value={draft.geography}
                onChange={(e) => update("geography", e.target.value)}
                className="focus-ring mt-4 w-full rounded border border-ink/20 bg-cream px-3 py-2 text-ink"
                placeholder="Geography"
              />
            </div>
          )}

          {currentKey === "outcome" && (
            <div>
              <h1 className="font-serif text-2xl text-ink">What outcome are you after?</h1>
              <p className="mt-1 text-sm text-ink/60">
                E.g. &quot;Land a summer internship&quot; or &quot;Get past resume screens&quot;.
              </p>
              <input
                autoFocus
                type="text"
                value={draft.outcome}
                onChange={(e) => update("outcome", e.target.value)}
                className="focus-ring mt-4 w-full rounded border border-ink/20 bg-cream px-3 py-2 text-ink"
                placeholder="Desired outcome"
              />
            </div>
          )}

          {currentKey === "job_description" && (
            <div>
              <h1 className="font-serif text-2xl text-ink">
                Paste a job description{" "}
                <span className="text-base font-normal text-ink/50">(optional)</span>
              </h1>
              <p className="mt-1 text-sm text-ink/60">
                If you have a specific posting in mind, pasting it helps scoring match its
                language. Skip this if you don&apos;t.
              </p>
              <textarea
                autoFocus
                value={draft.job_description}
                onChange={(e) => update("job_description", e.target.value)}
                rows={8}
                className="focus-ring mt-4 w-full rounded border border-ink/20 bg-cream px-3 py-2 text-ink"
                placeholder="Optional — paste the job posting text here"
              />
            </div>
          )}

          {error ? <p className="mt-3 text-sm text-red">{error}</p> : null}

          <div className="mt-8 flex items-center justify-between">
            <button
              type="button"
              onClick={goBack}
              disabled={step === 0}
              className="focus-ring rounded border border-ink/20 px-4 py-2 text-sm text-ink/70 disabled:opacity-30"
            >
              Back
            </button>
            <button
              type="submit"
              className="focus-ring rounded border border-teal bg-teal px-5 py-2 text-sm font-medium text-cream hover:opacity-90"
            >
              {step < STEPS.length - 1 ? "Next" : "Continue to upload"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
