import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the FastAPI backend runs on :8000; `npm run build` output is served by it directly.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
