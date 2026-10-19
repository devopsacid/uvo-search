/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Stable vendor chunks cache across deploys. cytoscape stays out of the
        // entry graph: only the lazy CytoscapeGraph chunk imports it.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          // clsx is used by both the app and recharts; pin it here so the entry never
          // statically imports the charts chunk.
          if (/node_modules\/(clsx|tailwind-merge)\//.test(id)) return 'vendor-react'
          if (/node_modules\/(react|react-dom|react-router|react-router-dom|@remix-run|scheduler)\//.test(id))
            return 'vendor-react'
          if (id.includes('@tanstack/')) return 'vendor-query'
          if (/node_modules\/(recharts|recharts-scale|d3-[^/]+|victory-vendor|internmap)\//.test(id))
            return 'vendor-charts'
          if (/node_modules\/(cytoscape|react-cytoscapejs)/.test(id)) return 'vendor-graph'
          return undefined
        },
      },
    },
  },
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/test/**', 'src/main.tsx', 'src/**/*.d.ts'],
      reporter: ['text-summary', 'html'],
      // Floors set ~10 points under current coverage; raise as tests are added.
      thresholds: { statements: 70, branches: 70, functions: 60, lines: 70 },
    },
    fakeTimers: {
      shouldAdvanceTime: true,
    },
  },
})
