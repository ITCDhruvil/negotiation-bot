/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        pit: "#14181F",
        bone: "#EEEAE2",
        amber: "#E09A3D",
        stitch: "#8A6A4B",
        ink: "#1A1714",
        ceiling: "#C0392B",
        deal: "#2E6B4F",
        fog: "#C9CDD3",
      },
      fontFamily: {
        display: ["var(--font-syne)", "sans-serif"],
        sans: ["var(--font-figtree)", "sans-serif"],
        mono: ["var(--font-plex)", "monospace"],
      },
      boxShadow: {
        dossier: "0 24px 60px rgba(20, 24, 31, 0.28)",
      },
      keyframes: {
        typing: {
          "0%, 100%": { transform: "translateY(0)", opacity: "0.5" },
          "50%": { transform: "translateY(-2px)", opacity: "1" },
        },
      },
      animation: {
        typing: "typing 1s infinite",
      },
    },
  },
  plugins: [],
};
