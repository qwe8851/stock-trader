/** @type {import('tailwindcss').Config} */
export default {
  // Enable class-based dark mode (toggle with class="dark" on <html>)
  darkMode: "class",

  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],

  theme: {
    extend: {
      colors: {
        // Chart-friendly neutral palette
        surface: {
          DEFAULT: "#0f0f14",
          50: "#1a1a24",
          100: "#16161f",
          200: "#12121a",
          300: "#0f0f14",
        },
        // Accent colours for trading UI
        bull: {
          DEFAULT: "#26a69a",  // green candle
          light: "#4db6ac",
          dark: "#00897b",
        },
        bear: {
          DEFAULT: "#ef5350",  // red candle
          light: "#ef9a9a",
          dark: "#c62828",
        },
        brand: {
          DEFAULT: "#6366f1",  // indigo
          light: "#818cf8",
          dark: "#4338ca",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-in-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(-4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },

  plugins: [],
};
