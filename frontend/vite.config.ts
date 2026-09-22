import react from '@vitejs/plugin-react';
// `vitest/config` rather than `vite` — it is the same `defineConfig` widened to accept the
// `test` block. Importing from `vite` and adding a triple-slash reference also works and is
// the older recipe; this one fails at the import rather than at the property, which is a
// better error to get.
import { defineConfig } from 'vitest/config';

/**
 * Vite + vitest in one config.
 *
 * The dev-server proxy is what makes `npm run dev` work without CORS gymnastics: the SPA calls
 * `/api/...` on its own origin and Vite forwards it, so there is no build-time API URL to
 * get wrong and no CORS configuration to keep in step between two repos.
 */
const api = process.env['VITE_API_BASE'] ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: api, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
});
