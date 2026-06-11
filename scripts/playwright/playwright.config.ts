import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173";
const artifactsDir = process.env.PLAYWRIGHT_ARTIFACTS_DIR ?? ".artifacts";
const expectTimeout = Number(process.env.PLAYWRIGHT_EXPECT_TIMEOUT_MS ?? 10_000);
const testTimeout = Number(process.env.PLAYWRIGHT_TEST_TIMEOUT_MS ?? 45_000);

export default defineConfig({
  testDir: "./tests",
  outputDir: `${artifactsDir}/test-results`,
  timeout: testTimeout,
  expect: {
    timeout: expectTimeout,
  },
  use: {
    baseURL,
    headless: true,
  },
  reporter: [["list"], ["html", { outputFolder: `${artifactsDir}/playwright-report` }]],
});
