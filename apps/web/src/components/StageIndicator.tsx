import type { Stage } from "@contracts/types";

const STAGE_LABELS: Record<Stage, string> = {
  ingest: "Ingest",
  extract: "Extract",
  normalize: "Normalize",
  score: "Score",
  recommend: "Recommend",
  audit: "Audit",
  publish: "Publish",
};

export function StageIndicator({
  stages,
  currentStage,
  failed = false,
}: {
  stages: readonly Stage[];
  currentStage: Stage;
  failed?: boolean;
}) {
  const currentIndex = stages.indexOf(currentStage);
  return (
    <ol className="flex flex-wrap items-center gap-x-1 gap-y-3">
      {stages.map((stage, index) => {
        const isCurrent = index === currentIndex;
        const isPast = index < currentIndex;
        return (
          <li key={stage} className="flex items-center">
            <span
              className={[
                "flex items-center gap-1.5 rounded-sm border px-2.5 py-1 text-xs font-medium",
                isCurrent && failed
                  ? "border-red/50 text-red"
                  : isCurrent
                    ? "border-teal bg-teal text-cream"
                    : isPast
                      ? "border-teal/40 text-teal"
                      : "border-ink/15 text-ink/40",
              ].join(" ")}
              aria-current={isCurrent ? "step" : undefined}
            >
              {isPast ? <span aria-hidden="true">✓</span> : null}
              {STAGE_LABELS[stage]}
            </span>
            {index < stages.length - 1 ? (
              <span className="mx-1 h-px w-4 bg-ink/15" aria-hidden="true" />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
