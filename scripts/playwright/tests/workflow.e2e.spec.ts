import { expect, test, type Page } from "@playwright/test";

const HIGH_RISK_DELAYED_MESSAGE =
  "Order ORD-1009 is delayed by 5 days. I need compensation.";
const LOW_RISK_LATE_MESSAGE = "Order ORD-1001 was late by one day.";
const DAMAGED_ITEM_MESSAGE = "Order ORD-1001 arrived broken.";

async function submitWorkflowMessage(page: Page, message: string) {
  const input = page.locator("textarea").first();
  await input.fill(message);
  await page.getByRole("button", { name: "Start Workflow" }).click();
}

test.describe("MAF workflow UI", () => {
  test("high-risk request triggers HITL and approve path completes", async ({
    page,
  }) => {
    await page.goto("/");
    const outputPanel = page.locator(".panel-output");
    const approvalPanel = page.locator(".panel-approval");

    await submitWorkflowMessage(page, HIGH_RISK_DELAYED_MESSAGE);

    await expect(
      page.getByText("hitl.request", { exact: false }),
    ).toBeVisible();
    await expect(approvalPanel.getByText("Order", { exact: true })).toBeVisible();
    await expect(approvalPanel.getByText("ord-1009", { exact: true })).toBeVisible();
    await page.locator("#approval-comment").fill("Approve delayed-order compensation");
    await page.getByRole("button", { name: "Approve" }).click();

    await expect(outputPanel).toContainText("Resolution complete");
    await expect(
      page.getByText("No pending approvals.", { exact: false }),
    ).toBeVisible();
  });

  test("low-risk request completes without HITL", async ({ page }) => {
    await page.goto("/");

    await submitWorkflowMessage(page, LOW_RISK_LATE_MESSAGE);

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
    const approvalPanel = page.locator(".panel-approval");

    await submitWorkflowMessage(page, DAMAGED_ITEM_MESSAGE);

    await expect(
      page.getByText("hitl.request", { exact: false }),
    ).toBeVisible();
    await expect(approvalPanel.getByText("ord-1001", { exact: true })).toBeVisible();
    await page.locator("#approval-comment").fill("Rejecting and escalating damaged order");
    await page.getByRole("button", { name: "Reject" }).click();

    await expect(outputPanel).toContainText('"status": "escalated"');
    await expect(
      page.getByText("No pending approvals.", { exact: false }),
    ).toBeVisible();
  });
});
