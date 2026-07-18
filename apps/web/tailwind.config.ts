import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        rxos: {
          bg: "#0b0f14",
          surface: "#131a22",
          accent: "#3ddc97",
        },
      },
    },
  },
  plugins: [],
};

export default config;
