import Link from "next/link";
import type { ReactNode } from "react";

// Small horizontal entry-point card — icon, title, one-line subtitle, chevron.
// Matches SectionCard's flat/no-shadow visual language.
export function PromoCard({
  href,
  icon,
  title,
  subtitle,
}: {
  href: string;
  icon: ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <Link
      href={href}
      className="focus-ring group flex items-center gap-4 rounded-md border border-ink/10 bg-cream px-4 py-3.5 transition-colors hover:border-teal/50"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-ink/10 text-teal">
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium text-ink">{title}</span>
        <span className="block truncate text-xs text-ink/60">{subtitle}</span>
      </span>
      <svg
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className="h-4 w-4 shrink-0 text-ink/40 transition-transform group-hover:translate-x-0.5 group-hover:text-teal"
      >
        <path d="M7.5 4.5l5.5 5.5-5.5 5.5" />
      </svg>
    </Link>
  );
}
