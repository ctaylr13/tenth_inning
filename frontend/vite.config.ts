import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import wyw from '@wyw-in-js/vite'

export default defineConfig({
  plugins: [
    react(),
    wyw({
      include: ['**/*.{ts,tsx}'],
      exclude: ['**/node_modules/**'],
      babelOptions: {
        presets: ['@babel/preset-typescript', '@babel/preset-react'],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        // 127.0.0.1, not localhost -- localhost can resolve to ::1 and hit
        // Docker Desktop's *:8000 instead of the API.
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        // Websockets are not proxied unless you ask. Without this the
        // handshake gets a plain 200 from Vite instead of a 101, and the
        // client sees a close with no code -- the failure mode the socket
        // hook's giving-up branch exists for.
        ws: true,
      },
    },
  },
})