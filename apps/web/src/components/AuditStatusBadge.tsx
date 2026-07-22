import type { AuditStatus } from "@contracts/types";

const AUDIT_STYLES: Record<AuditStatus, { label: string; className: string }> = {
  supported: { label: "Supported", className: "border-teal/40 text-teal" },
  unsupported: { label: "Unsupported", className: "border-red/40 text-red" },
  contradictory: { label: "Contradictory", className: "border-red/40 text-red" },
  vague: { label: "Vague", className: "border-amber/50 text-amber" },
  not_audited: { label: "Not audited", className: "border-ink/20 text-ink/50" },
};

export function AuditStatusBadge({ status }: { status: AuditStatus }) {
  const style = AUDIT_STYLES[status];
  return (
    <span className={`inline-block rounded-sm border px-2 py-0.5 text-xs font-medium ${style.className}`}>
      {style.label}
    </span>
  );
}
