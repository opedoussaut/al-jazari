/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#1d1d1f", soft: "#424245", mute: "#6e6e73" },
        line: "#e5e5ea",
        mist: "#f5f5f7",
        navy: { DEFAULT: "#0a3d7a", deep: "#062a57", soft: "#e8f0fa" },
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "'SF Pro Text'", "'Segoe UI'", "Inter", "Roboto", "sans-serif"],
        mono: ["'SF Mono'", "ui-monospace", "Consolas", "monospace"],
      },
      boxShadow: { card: "0 1px 2px rgba(0,0,0,.04), 0 4px 16px rgba(0,0,0,.04)" },
    },
  },
  plugins: [],
};
