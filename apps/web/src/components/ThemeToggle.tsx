"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "profilepilot-theme";

function SunIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      <circle cx="10" cy="10" r="3.25" />
      <path d="M10 1.75v2.1M10 16.15v2.1M18.25 10h-2.1M3.85 10h-2.1M15.66 4.34l-1.48 1.48M5.82 14.18l-1.48 1.48M15.66 15.66l-1.48-1.48M5.82 5.82L4.34 4.34" />
    </svg>
  );
}

function MoonIcon() {
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
      <path d="M17 11.5A7.2 7.2 0 118.5 3a5.6 5.6 0 108.5 8.5z" />
    </svg>
  );
}

export function ThemeToggle() {
  // Starts null so the server-rendered and pre-hydration client markup
  // match exactly; the real value is read from the DOM (already set by the
  // blocking script in layout.tsx) right after mount.
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const current = document.documentElement.getAttribute("data-theme");
    setTheme(current === "dark" ? "dark" : "light");
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // localStorage unavailable (private browsing, etc.) — theme still
      // applies for this page load, it just won't persist.
    }
    setTheme(next);
  }

  const displayTheme = theme ?? "light";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={displayTheme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="focus-ring flex h-7 w-7 items-center justify-center rounded-sm border border-ink/15 text-ink/70 transition-colors hover:border-teal hover:text-teal"
    >
      {displayTheme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}
