import type { Config } from "tailwindcss";

// Visual system: "career dossier / editorial workbench" — warm paper tones,
// crisp document rules, no gradients/glass/oversized hero type. See
// docs/adr/0004-visual-system.md.
const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./src/**/*.{ts,tsx}", "../../packages/contracts/src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // RGB-triplet CSS variables (see globals.css) wrapped so opacity
        // modifiers like bg-cream/50 keep working across themes.
        cream: "rgb(var(--color-cream) / <alpha-value>)",
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        teal: "rgb(var(--color-teal) / <alpha-value>)",
        amber: "rgb(var(--color-amber) / <alpha-value>)",
        red: "rgb(var(--color-red) / <alpha-value>)",
      },
      fontFamily: {
        serif: ["var(--font-source-serif)", "Georgia", "serif"],
        sans: ["var(--font-ibm-plex-sans)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
      },
      boxShadow: {
        none: "none",
      },
    },
  },
  plugins: [],
};

export default config;
