"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

interface NavItem {
  href: string;
  label: string;
  // Routes that should light this item up as active — the analysis flow
  // spans several route segments (intake -> upload -> analyses/*) that all
  // belong to the same "Analyze Profile" entry point.
  activePrefixes: string[];
  icon: ReactNode;
}

function AnalyzeIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      <circle cx="8.5" cy="8.5" r="5.5" />
      <path d="M16.25 16.25l-3.6-3.6" />
    </svg>
  );
}

function ScribeIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      <path d="M13.5 2.5l4 4-9 9-4.5 1 1-4.5z" />
      <path d="M11.5 4.5l4 4" />
    </svg>
  );
}

function PrivacyIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      <path d="M10 2.3l6.2 2.2v4.9c0 4.1-2.7 6.9-6.2 8.1-3.5-1.2-6.2-4-6.2-8.1V4.5z" />
      <path d="M7.3 10l1.9 1.9 3.5-3.9" />
    </svg>
  );
}

const NAV_ITEMS: NavItem[] = [
  {
    href: "/upload",
    label: "Analyze Profile",
    activePrefixes: ["/intake", "/upload", "/analyses"],
    icon: <AnalyzeIcon />,
  },
  {
    href: "/scribe",
    label: "Scribe",
    activePrefixes: ["/scribe"],
    icon: <ScribeIcon />,
  },
  {
    href: "/privacy",
    label: "Privacy",
    activePrefixes: ["/privacy"],
    icon: <PrivacyIcon />,
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-ink/10 bg-cream px-3 py-6">
      <Link href="/" className="focus-ring mb-8 block rounded-sm px-2.5 font-serif text-lg text-ink">
        ProfilePilot
      </Link>
      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const active = item.activePrefixes.some((prefix) => pathname.startsWith(prefix));
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`focus-ring flex items-center gap-2.5 rounded-sm px-2.5 py-2 text-sm transition-colors ${
                active
                  ? "bg-teal/10 font-medium text-teal"
                  : "text-ink/70 hover:bg-ink/5 hover:text-ink"
              }`}
            >
              {item.icon}
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
