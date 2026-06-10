import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173";
const artifactsDir = ".artifacts";

export default defineConfig({
  testDir: "./tests",
  outputDir: `${artifactsDir}/test-results`,
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL,
    headless: true,
  },
  reporter: [["list"], ["html", { outputFolder: `${artifactsDir}/playwright-report` }]],
});
