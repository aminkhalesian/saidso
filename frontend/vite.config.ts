import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// `npm run build:static` makes one self-contained HTML file with a data snapshot inside (no server needed).
// The single-file plugin is only loaded for that build, so a normal build never needs it installed.
const STATIC = process.env.VITE_STATIC === "1";
const extra = STATIC ? [(await import("vite-plugin-singlefile")).viteSingleFile()] : [];

export default defineConfig({
  plugins: [react(), tailwindcss(), ...extra],
  resolve: {
    alias: { "snapshot-data": path.resolve(__dirname, STATIC ? "static-snapshot.json" : "src/snapshot-stub.json") },
  },
  server: { proxy: { "/api": "http://localhost:8000" } },
});
