/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Tokens live in web/src/ui/tokens.css (docs/03_UI_Spec.md §10).
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        fg: "var(--text)",
        muted: "var(--text-muted)",
        accent: "var(--accent)",
        "accent-ink": "var(--accent-ink)",
        ok: "var(--ok)",
        error: "var(--error)",
        focus: "var(--focus)",
        "dev-missed": "var(--dev-missed)",
        "dev-order": "var(--dev-order)",
        "dev-tool": "var(--dev-tool)",
        "needs-review": "var(--needs-review)",
        illustration: "var(--illustration)",
      },
      fontFamily: {
        ui: "var(--font-ui)",
        mono: "var(--font-mono)",
      },
      fontSize: {
        small: ["var(--text-small)", { lineHeight: "var(--line-small)" }],
        control: ["var(--text-control)", { lineHeight: "var(--line-control)" }],
        base: ["var(--text-base)", { lineHeight: "var(--line-base)" }],
        h3: ["var(--text-h3)", { lineHeight: "var(--line-h3)" }],
        h2: ["var(--text-h2)", { lineHeight: "var(--line-h2)" }],
        h1: ["var(--text-h1)", { lineHeight: "var(--line-h1)" }],
      },
      borderRadius: {
        control: "var(--radius-control)",
        card: "var(--radius-card)",
        chip: "var(--radius-chip)",
        modal: "var(--radius-modal)",
      },
      boxShadow: {
        modal: "var(--shadow-modal)",
      },
      transitionDuration: {
        fast: "var(--motion-fast)",
        panel: "var(--motion-panel)",
      },
      maxWidth: {
        page: "var(--page-max-width)",
      },
    },
  },
  plugins: [],
};
