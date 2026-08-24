import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],

  server: {
    proxy: {
      "/api": {
        target: "http://52.20.107.132:18000",
        changeOrigin: true,
      },
    },
  },
});