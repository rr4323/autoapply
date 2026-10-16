import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // No CORS support on the Go API yet (Phase 1, single-origin
    // assumption per docs/TDD.md §16's SSO/session-auth blind spot) —
    // proxying avoids needing it in dev, and mirrors how a real
    // deployment would sit both apps behind one reverse-proxied origin.
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
})
