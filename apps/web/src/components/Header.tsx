import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";

export function Header() {
  return (
    <header className="border-b border-ink/10">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
        <Link
          href="/"
          className="focus-ring rounded-sm font-serif text-lg text-ink"
        >
          ProfilePilot
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          <Link
            href="/privacy"
            className="focus-ring rounded-sm text-ink/70 transition-colors hover:text-teal"
          >
            Privacy
          </Link>
          <span className="rounded-sm border border-ink/15 px-2 py-1 text-xs text-ink/60">
            dev@local.test
          </span>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}
