import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        surface: "var(--bg-2)",
        panel: "var(--bg-3)",
        line: "var(--line-2)",
        signal: {
          cyan: "var(--signal-cyan)",
          violet: "var(--signal-violet)",
          lime: "var(--signal-lime)",
          amber: "var(--signal-amber)",
          orange: "var(--signal-orange)",
          rose: "var(--signal-rose)",
          emerald: "var(--signal-emerald)",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        display: ["var(--font-display)"],
        mono: ["var(--font-mono)"],
      },
      boxShadow: {
        panel: "var(--shadow-panel)",
        "glow-cyan": "var(--shadow-glow-cyan)",
        "glow-violet": "var(--shadow-glow-violet)",
      },
    },
  },
  plugins: [],
};
export default config;
