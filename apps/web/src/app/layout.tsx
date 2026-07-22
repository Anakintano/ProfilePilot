import type { Metadata } from "next";
import { Source_Serif_4, IBM_Plex_Sans } from "next/font/google";
import "../styles/globals.css";

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
  display: "swap",
});

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-ibm-plex-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ProfilePilot — Career profile diagnostics",
  description:
    "Upload your LinkedIn PDF, screenshots, or résumé and get an explainable, evidence-backed report with scores, rewrites, and a prioritized action plan.",
};

// Runs before hydration so the correct theme is set before first paint —
// avoids a flash of the wrong theme. Can't be a useEffect (too late, that
// runs after paint). suppressHydrationWarning on <html> below is required
// because this script mutates the data-theme attribute outside of React.
const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("profilepilot-theme");if(t!=="light"&&t!=="dark"){t=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";}document.documentElement.setAttribute("data-theme",t);}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${sourceSerif.variable} ${ibmPlexSans.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="font-sans antialiased min-h-screen">{children}</body>
    </html>
  );
}
