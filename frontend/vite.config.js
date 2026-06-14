import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(process.cwd(), '..'), '')
  const apiPort = env.API_PORT || 8000

  return {
    plugins: [react()],
    server: {
      port: 5173,
      allowedHosts: ['fitting-internal-hookworm.ngrok-free.app'],
      proxy: {
        '/api': {
          target: `http://localhost:${apiPort}`,
          changeOrigin: true,
        },
      },
    },
  }
})
