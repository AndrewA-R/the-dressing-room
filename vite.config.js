import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vercel serves the built SPA from /dist and the functions in /api automatically.
export default defineConfig({
  plugins: [react()],
})
