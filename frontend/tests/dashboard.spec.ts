import { test, expect } from "@playwright/test";

test.describe("Match Dashboard", () => {
  test("shows empty state when no jobs exist", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Lazy Matcher" })).toBeVisible();
    await expect(page.getByText("No results yet")).toBeVisible();
  });

  test("validates form input", async ({ page }) => {
    await page.goto("/");

    // Submit button should be disabled when textarea is empty
    const submitBtn = page.getByRole("button", { name: /submit/i });
    await expect(submitBtn).toBeDisabled();

    // Type something short - should show validation error (use pressSequentially to trigger React onChange)
    await page.locator("#descriptions").pressSequentially("hi");
    await expect(page.getByText(/too short to score/)).toBeVisible({ timeout: 5000 });
    await expect(submitBtn).toBeDisabled();
  });

  test("shows validation for too many items", async ({ page }) => {
    await page.goto("/");

    const lines = Array.from(
      { length: 12 },
      (_, i) =>
        `Job description number ${i + 1} with enough text to pass minimum length validation`
    ).join("\n");
    // fill() doesn't trigger React onChange on controlled textareas, so dispatch input event
    await page.locator("#descriptions").fill(lines);
    await page.locator("#descriptions").evaluate((el) =>
      el.dispatchEvent(new Event("input", { bubbles: true }))
    );

    await expect(page.getByText(/Maximum 10 items/)).toBeVisible({ timeout: 10000 });
  });

  test("status filter dropdown works", async ({ page }) => {
    await page.goto("/");

    const filter = page.locator('select[aria-label="Status filter"]');
    await expect(filter).toBeVisible();

    // Select a filter
    await filter.selectOption("completed");
    // Page should still be visible (no crash)
    await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
  });

  test("randomize button populates form", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: /randomize/i }).click();

    const textarea = page.locator("#descriptions");
    const value = await textarea.inputValue();
    expect(value.length).toBeGreaterThan(50);
  });
});

test.describe("Polling behavior", () => {
  test("page polls and updates without reload", async ({ page }) => {
    await page.goto("/");

    // Wait for initial load
    await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();

    // Check that the page has polling indicators
    await expect(page.getByText("Polling every 3s")).toBeVisible();

    // Verify the page doesn't reload (check that form content persists)
    // fill() doesn't trigger React onChange, so dispatch input event after
    await page.locator("#descriptions").fill("Test content for persistence check");
    await page.locator("#descriptions").evaluate((el) =>
      el.dispatchEvent(new Event("input", { bubbles: true }))
    );
    await page.waitForTimeout(5000);

    // Content should still be there (no page reload)
    const value = await page.locator("#descriptions").inputValue();
    expect(value).toBe("Test content for persistence check");
  });
});
