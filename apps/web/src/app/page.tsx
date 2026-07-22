import Image from "next/image";
import Link from "next/link";
import { Header } from "@/components/Header";
import { PromoCard } from "@/components/PromoCard";

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <Header />
      <main>
        <section className="mx-auto max-w-5xl px-6 py-14">
          <div className="grid items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
            <div>
              <p className="font-sans text-sm uppercase tracking-wide text-teal">
                Career profile diagnostic
              </p>
              <h1 className="mt-3 font-serif text-4xl leading-tight text-ink">
                See how your résumé or LinkedIn profile reads against the role you want.
              </h1>
              <p className="mt-6 max-w-xl text-base leading-relaxed text-ink/80">
                Upload your résumé or a LinkedIn export, tell us the role you&apos;re targeting,
                and ProfilePilot scores your profile against that goal with evidence-backed
                reasoning — not a black-box grade. Every score cites the text it came from, and
                every rewrite suggestion is checked against your actual document before it&apos;s
                shown to you.
              </p>
              <Link
                href="/intake"
                className="focus-ring mt-8 inline-block rounded border border-teal bg-teal px-6 py-3 text-sm font-medium text-cream transition-opacity hover:opacity-90"
              >
                Analyse my profile
              </Link>
            </div>

            <div className="relative aspect-[4/3] overflow-hidden rounded-md border border-ink/10">
              <Image
                src="/images/hero-resume-review.jpg"
                alt="A candidate reviewing a résumé draft on a laptop"
                fill
                priority
                sizes="(min-width: 1024px) 480px, 100vw"
                className="object-cover"
              />
            </div>
          </div>
        </section>

        <div className="mx-auto max-w-3xl px-6 pb-14">
          <div className="border-l-2 border-amber/60 pl-4">
            <p className="text-sm leading-relaxed text-ink/70">
              <strong className="text-ink">A limitation worth stating up front:</strong> scores
              are a coaching aid, not a hiring prediction. No score here tells you whether a
              recruiter will call you back — it tells you where your document is strong, where
              it&apos;s thin, and what to fix first.
            </p>
          </div>

          <div className="mt-6 border-l-2 border-teal/60 pl-4">
            <p className="text-sm leading-relaxed text-ink/70">
              <strong className="text-ink">Privacy promise:</strong> raw uploads are automatically
              deleted 24 hours after you submit them. Read more on the{" "}
              <Link href="/privacy" className="focus-ring rounded-sm text-teal underline underline-offset-2">
                privacy page
              </Link>
              .
            </p>
          </div>

          <div className="mt-12">
            <p className="text-xs uppercase tracking-wide text-ink/50">Get started</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <PromoCard
                href="/intake"
                title="Analyse my profile"
                subtitle="Score your résumé or LinkedIn export against a target role."
                icon={
                  <svg
                    viewBox="0 0 20 20"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                    className="h-5 w-5"
                  >
                    <circle cx="8.5" cy="8.5" r="5.5" />
                    <path d="M16.5 16.5l-3.6-3.6" />
                  </svg>
                }
              />
              <PromoCard
                href="/scribe"
                title="Try Scribe"
                subtitle="Draft LinkedIn posts and comments in your voice."
                icon={
                  <svg
                    viewBox="0 0 20 20"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                    className="h-5 w-5"
                  >
                    <path d="M13.5 2.5l4 4-9 9-4.5 1 1-4.5z" />
                    <path d="M11.5 4.5l4 4" />
                  </svg>
                }
              />
            </div>
          </div>

          <div className="mt-12 border-t border-ink/10 pt-8">
            <h2 className="font-serif text-xl text-ink">How it works</h2>
            <ol className="mt-4 space-y-3 text-sm text-ink/75">
              <li>
                <span className="font-medium text-ink">1. Tell us your target role.</span> Role,
                seniority, geography, and what outcome you&apos;re after.
              </li>
              <li>
                <span className="font-medium text-ink">2. Upload your résumé or LinkedIn export.</span>{" "}
                PDF or a clear screenshot works.
              </li>
              <li>
                <span className="font-medium text-ink">3. Review the extraction.</span> Confirm
                what we read from your document before scoring runs.
              </li>
              <li>
                <span className="font-medium text-ink">4. Get a scored, cited report.</span>{" "}
                Dimension-by-dimension scores, audited rewrite suggestions, and a prioritized
                action plan.
              </li>
            </ol>
          </div>
        </div>
      </main>
    </div>
  );
}
