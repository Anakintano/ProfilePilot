import type { ReactNode } from "react";

export function SectionCard({
  title,
  headingLevel = "h2",
  action,
  children,
}: {
  title?: string;
  headingLevel?: "h2" | "h3";
  action?: ReactNode;
  children: ReactNode;
}) {
  const Heading = headingLevel;
  return (
    <section className="rounded-md border border-ink/10 bg-cream p-5">
      {title ? (
        <div className="mb-3 flex items-center justify-between gap-3">
          <Heading className="font-serif text-lg text-ink">{title}</Heading>
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}
