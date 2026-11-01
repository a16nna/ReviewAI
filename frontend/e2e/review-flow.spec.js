import { expect, test } from "@playwright/test";

test("submit code, export, open from history, delete, check settings", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Open review workspace" }).click();
  await page.getByRole("button", { name: "Analyze" }).click(); // the sample snippet uses eval()
  await expect(page.getByText("MOCK MODE")).toBeVisible();
  await expect(page.getByRole("heading", { name: /B307/ })).toBeVisible();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Export Markdown" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^review-.*\.md$/);

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "History" }).click();
  await page.getByRole("table").getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: /B307/ })).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page).toHaveURL(/\/history$/);

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Settings" }).click();
  await expect(page.getByText(/Mode: demo \(mock AI\)/)).toBeVisible();
});
