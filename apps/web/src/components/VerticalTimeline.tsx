export type TimelineStepStatus = "done" | "current" | "pending" | "failed";

export interface TimelineStep {
  label: string;
  description: string;
  status: TimelineStepStatus;
  timestamp?: string;
}

function StepMarker({ status }: { status: TimelineStepStatus }) {
  if (status === "done") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full border border-teal bg-teal text-cream">
        <svg
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className="h-3 w-3"
        >
          <path d="M2.5 6.2l2.3 2.3 4.7-5" />
        </svg>
      </span>
    );
  }
  if (status === "current") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full border-2 border-teal">
        <span className="h-2 w-2 rounded-full bg-teal" />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full border border-red bg-red text-cream">
        <svg
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          aria-hidden="true"
          className="h-3 w-3"
        >
          <path d="M3 3l6 6M9 3l-6 6" />
        </svg>
      </span>
    );
  }
  return <span className="block h-5 w-5 rounded-full border border-ink/25" />;
}

// Vertical checkmark-per-step layout with a description and optional
// timestamp per step — richer than the horizontal pill-stepper StageIndicator.
export function VerticalTimeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <ol>
      {steps.map((step, index) => (
        <li
          key={step.label}
          aria-current={step.status === "current" ? "step" : undefined}
          className="relative flex gap-3 pb-6 last:pb-0"
        >
          {index < steps.length - 1 ? (
            <span
              aria-hidden="true"
              className={`absolute left-[9px] top-5 h-[calc(100%-1.25rem)] w-px ${
                step.status === "done" ? "bg-teal/40" : "bg-ink/15"
              }`}
            />
          ) : null}
          <span className="relative z-10 mt-0.5 shrink-0">
            <StepMarker status={step.status} />
          </span>
          <div className="min-w-0 flex-1 pt-0.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <p
                className={`text-sm font-medium ${
                  step.status === "failed"
                    ? "text-red"
                    : step.status === "pending"
                      ? "text-ink/40"
                      : "text-ink"
                }`}
              >
                {step.label}
              </p>
              {step.timestamp ? <span className="text-xs text-ink/40">{step.timestamp}</span> : null}
            </div>
            <p className={`mt-0.5 text-xs ${step.status === "pending" ? "text-ink/35" : "text-ink/60"}`}>
              {step.description}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
