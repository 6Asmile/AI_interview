import { defineConfig } from '@playwright/test';

const documentationVirtualMedia = process.env.IFACEOFF_DOCS_VIRTUAL_MEDIA === '1';

export default defineConfig({
  testDir: './tests/e2e',
  outputDir: '../logs/playwright-results',
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never', outputFolder: '../logs/playwright-report' }]],
  use: {
    baseURL: process.env.IFACEOFF_E2E_BASE_URL || 'http://127.0.0.1:5173',
    channel: 'msedge',
    headless: true,
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    permissions: documentationVirtualMedia ? ['camera', 'microphone'] : [],
    launchOptions: {
      args: documentationVirtualMedia
        ? ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream']
        : [],
    },
  },
});
