export function confidenceLabel(confidence: number | null): {
  label: string;
  className: string;
} {
  if (confidence === null) {
    return { label: "Confidence unknown", className: "border-ink/20 text-ink/50" };
  }
  if (confidence < 0.5) {
    return { label: `Low confidence (${Math.round(confidence * 100)}%)`, className: "border-red/40 text-red" };
  }
  if (confidence < 0.75) {
    return { label: `Medium confidence (${Math.round(confidence * 100)}%)`, className: "border-amber/50 text-amber" };
  }
  return { label: `High confidence (${Math.round(confidence * 100)}%)`, className: "border-teal/40 text-teal" };
}

export function ConfidenceTag({ confidence }: { confidence: number | null }) {
  const { label, className } = confidenceLabel(confidence);
  return (
    <span className={`inline-block rounded-sm border px-2 py-0.5 text-xs font-medium ${className}`}>
      {label}
    </span>
  );
}
