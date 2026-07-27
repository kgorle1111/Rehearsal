import { defineConfig } from 'vitest/config';

// kn: dev-only proxy; production is served by rehearsal-api as a static mount (10-frontend-spec.md §2.3)
export default defineConfig({
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8420',
      '/ws': { target: 'ws://127.0.0.1:8420', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    target: 'es2022',
  },
  test: {
    environment: 'jsdom',
    include: ['test/**/*.test.ts'],
    globals: false,
  },
});
