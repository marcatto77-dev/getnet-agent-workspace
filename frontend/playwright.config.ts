import { defineConfig } from '@playwright/test'
const externalBaseUrl=process.env.PLAYWRIGHT_BASE_URL
export default defineConfig({
  testDir: './tests', use: {baseURL:externalBaseUrl||'http://127.0.0.1:5173', headless:true},
  webServer: externalBaseUrl?undefined:{command:'npm run dev',url:'http://127.0.0.1:5173',reuseExistingServer:true},
})
