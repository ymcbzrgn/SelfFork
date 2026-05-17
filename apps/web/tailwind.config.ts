import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        // ── Stitch-generated Material-3 vocabulary (raw hex) ───────
        // Pages ported verbatim from Stitch use these class names.
        "on-surface": "#191b23",
        "on-surface-variant": "#434655",
        "on-background": "#191b23",
        "foreground-muted": "#7B7B8F",
        "outline": "#737686",
        "outline-variant": "#c3c6d7",
        surface: "#FFFFFF",
        "surface-muted": "#F1F1F6",
        "surface-bright": "#faf8ff",
        "surface-dim": "#d9d9e5",
        "surface-variant": "#e1e2ed",
        "surface-tint": "#0053db",
        "surface-container-lowest": "#FFFFFF",
        "surface-container-low": "#f3f3fe",
        "surface-container": "#ededf9",
        "surface-container-high": "#e7e7f3",
        "surface-container-highest": "#e1e2ed",
        "primary-container": "#2563eb",
        "on-primary-container": "#eeefff",
        "on-primary-fixed": "#00174b",
        "on-primary-fixed-variant": "#003ea8",
        "primary-fixed": "#dbe1ff",
        "primary-fixed-dim": "#b4c5ff",
        "inverse-primary": "#b4c5ff",
        "secondary-container": "#dfdfe7",
        "on-secondary-container": "#616269",
        "secondary-fixed": "#e2e2ea",
        "secondary-fixed-dim": "#c5c6ce",
        "on-secondary-fixed": "#191b21",
        "on-secondary-fixed-variant": "#45464d",
        tertiary: "#943700",
        "tertiary-container": "#bc4800",
        "on-tertiary": "#ffffff",
        "on-tertiary-container": "#ffede6",
        "tertiary-fixed": "#ffdbcd",
        "tertiary-fixed-dim": "#ffb596",
        "on-tertiary-fixed": "#360f00",
        "on-tertiary-fixed-variant": "#7d2d00",
        "error-container": "#ffdad6",
        "on-error": "#ffffff",
        "on-error-container": "#93000a",
        "inverse-surface": "#2e3039",
        "inverse-on-surface": "#f0f0fb",
        // ── Existing shadcn vocabulary (HSL via CSS vars) ────────────
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        info: {
          DEFAULT: "hsl(var(--info))",
          foreground: "hsl(var(--info-foreground))",
        },
        error: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar))",
          foreground: "hsl(var(--sidebar-foreground))",
          border: "hsl(var(--sidebar-border))",
          accent: "hsl(var(--sidebar-accent))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      spacing: {
        // SelfFork v2 design tokens (Stitch design system aligned).
        "topbar-height": "64px",
        "gutter-desktop": "40px",
        "card-padding": "24px",
        "vertical-gap": "24px",
        "sidebar-width": "240px",
      },
      fontFamily: {
        // All Stitch typography classes (font-display / font-heading /
        // font-body / font-caption / font-display-mobile) route to Inter
        // via the CSS variable installed by next/font/google in
        // app/layout.tsx.
        sans: ["var(--font-inter)", "Inter", "sans-serif"],
        display: ["var(--font-inter)", "Inter", "sans-serif"],
        heading: ["var(--font-inter)", "Inter", "sans-serif"],
        body: ["var(--font-inter)", "Inter", "sans-serif"],
        caption: ["var(--font-inter)", "Inter", "sans-serif"],
        "display-mobile": ["var(--font-inter)", "Inter", "sans-serif"],
      },
      fontSize: {
        display: [
          "32px",
          { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600" },
        ],
        "display-mobile": [
          "28px",
          { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600" },
        ],
        heading: [
          "20px",
          { lineHeight: "1.4", letterSpacing: "-0.01em", fontWeight: "600" },
        ],
        body: [
          "16px",
          { lineHeight: "1.5", letterSpacing: "0", fontWeight: "400" },
        ],
        caption: [
          "13px",
          { lineHeight: "1.4", letterSpacing: "0", fontWeight: "500" },
        ],
      },
      boxShadow: {
        card: "0 2px 8px rgba(15, 23, 42, 0.04)",
        "card-hover": "0 4px 16px rgba(15, 23, 42, 0.06)",
      },
      keyframes: {
        "pulse-red": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.3" },
        },
      },
      animation: {
        "pulse-red": "pulse-red 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
