import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  use: {
    baseURL: process.env.PREVIEW_URL ?? 'http://127.0.0.1:8080',
    browserName: 'chromium',
    trace: 'retain-on-failure',
  },
  retries: 0,
  workers: 1,
});
