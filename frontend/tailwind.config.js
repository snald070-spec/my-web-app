export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      // ── Brand colour palette — customise here ──────────────────────
      // Default: blue-600 = #2563eb (standard Tailwind blue)
      // Example override to a custom brand red (#E52222):
      //
      // colors: {
      //   blue: {
      //     50:  "#FEF0F0",
      //     100: "#FDDADA",
      //     200: "#FAB0B0",
      //     300: "#F57878",
      //     400: "#EE4646",
      //     500: "#E82A2A",
      //     600: "#E52222",   // ← Primary brand colour
      //     700: "#B81A1A",
      //     800: "#8C1414",
      //     900: "#600D0D",
      //   },
      // },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        // Korean project: ["Pretendard", "'Apple SD Gothic Neo'", "'Noto Sans KR'", "system-ui", "sans-serif"]
      },
      boxShadow: {
        card:    "0 1px 3px rgba(0,0,0,0.07), 0 4px 16px rgba(0,0,0,0.05)",
        modal:   "0 20px 60px rgba(0,0,0,0.20)",
        header:  "0 1px 0 rgba(0,0,0,0.08)",
      },
      keyframes: {
        "fade-in":  { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        "scale-in": { from: { opacity: "0", transform: "scale(0.95)" },     to: { opacity: "1", transform: "scale(1)" } },
        "skeleton-shine": {
          "0%":   { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition:  "200% 0" },
        },
      },
      animation: {
        "fade-in":  "fade-in 0.22s ease both",
        "scale-in": "scale-in 0.20s ease both",
        "skeleton": "skeleton-shine 1.6s linear infinite",
      },
    },
  },
  plugins: [],
}
