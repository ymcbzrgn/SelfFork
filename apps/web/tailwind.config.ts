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
        "on-surface": "#222722",
        "on-surface-variant": "#59605a",
        "on-background": "#222722",
        "foreground-muted": "#8f968f",
        "outline": "#8f968f",
        "outline-variant": "#d9dcd7",
        surface: "#FFFFFF",
        "surface-muted": "#f1f3f0",
        "surface-bright": "#f8f9f7",
        "surface-dim": "#d9dcd7",
        "surface-variant": "#e5e7e2",
        "surface-tint": "#45927a",
        "surface-container-lowest": "#FFFFFF",
        "surface-container-low": "#f8f9f7",
        "surface-container": "#f1f3f0",
        "surface-container-high": "#eaecea",
        "surface-container-highest": "#e5e7e2",
        "primary-container": "#45927a",
        "on-primary-container": "#ffffff",
        "on-primary-fixed": "#123a2e",
        "on-primary-fixed-variant": "#2a5f4f",
        "primary-fixed": "#e2ece7",
        "primary-fixed-dim": "#a9cfc1",
        "inverse-primary": "#45927a",
        "secondary-container": "#dfdfe7",
        "on-secondary-container": "#616269",
        "secondary-fixed": "#e2e2ea",
        "secondary-fixed-dim": "#c5c6ce",
        "on-secondary-fixed": "#191b21",
        "on-secondary-fixed-variant": "#45464d",
        tertiary: "#943700",
        "tertiary-container": "#a1712b",
        "on-tertiary": "#ffffff",
        "on-tertiary-container": "#ffede6",
        "tertiary-fixed": "#f0e6d3",
        "tertiary-fixed-dim": "#e2c68f",
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
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        display: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        heading: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        body: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        caption: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        "display-mobile": ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
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
