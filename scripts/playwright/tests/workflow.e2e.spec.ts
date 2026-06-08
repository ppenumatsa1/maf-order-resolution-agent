import { expect, test } from "@playwright/test";

test.describe("MAF workflow UI", () => {
  test("high-risk request triggers HITL and approve path completes", async ({
    page,
  }) => {
    await page.goto("/");
    const outputPanel = page.locator(".panel-output");

    await page.getByRole("button", { name: "Start Workflow" }).click();

    await expect(
      page.getByText("hitl.request", { exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Approve" }).click();

    await expect(outputPanel).toContainText("Resolution complete");
  });

  test("low-risk request completes without HITL", async ({ page }) => {
    await page.goto("/");

    const input = page.locator("textarea");
    await input.fill("Order ORD-1001 was late by one day.");
    await page.getByRole("button", { name: "Start Workflow" }).click();

    await expect(
      page.getByText("workflow.output", { exact: false }),
    ).toBeVisible();
    await expect(
      page.getByText("No pending approvals.", { exact: false }),
    ).toBeVisible();
  });

  test("reject decision escalates workflow", async ({ page }) => {
    await page.goto("/");
    const outputPanel = page.locator(".panel-output");

    const input = page.locator("textarea");
    await input.fill("Order ORD-2009 came damaged and broken.");
    await page.getByRole("button", { name: "Start Workflow" }).click();

    await expect(
      page.getByText("hitl.request", { exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Reject" }).click();

    await expect(outputPanel).toContainText('"status": "escalated"');
  });
});
