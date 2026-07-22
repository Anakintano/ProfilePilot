import type { ImpactEffort } from "@contracts/types";

export function ImpactEffortBadge({ label, value }: { label: string; value: ImpactEffort }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border border-ink/15 px-2 py-0.5 text-xs text-ink/70">
      <span className="text-ink/50">{label}</span>
      <span className="font-medium capitalize text-ink">{value}</span>
    </span>
  );
}
