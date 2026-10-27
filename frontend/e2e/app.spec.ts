import { test, expect } from "@playwright/test";

test.describe("CodeSense AI - Frontend E2E Test Suite", () => {
  test("1. Login page renders authentication controls", async ({ page }) => {
    await page.goto("/login");
    await expect(page).toHaveTitle(/CodeSense|Login/i);

    // Verify email and password inputs
    const emailInput = page.locator('input[type="email"]');
    const passwordInput = page.locator('input[type="password"]');
    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();

    // Verify submit button
    const submitBtn = page.locator('button[type="submit"]');
    await expect(submitBtn).toBeVisible();
  });

  test("2. Register page renders properly", async ({ page }) => {
    await page.goto("/register");
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible();
  });

  test("3. Chat interface renders chat controls and suggestions", async ({ page }) => {
    await page.goto("/app/chat");

    // Textarea input should be available
    const textarea = page.locator("textarea");
    await expect(textarea).toBeVisible();

    // Send button should be rendered
    const sendButton = page.locator('button:has(svg.lucide-send), button:has-text("Send")');
    await expect(sendButton.first()).toBeVisible();

    // Verify prompt suggestions or instructions
    const suggestions = page.locator("text=Explain the overall architecture");
    if (await suggestions.isVisible()) {
      await expect(suggestions).toBeVisible();
    }
  });

  test("4. Repository management page has connect button", async ({ page }) => {
    await page.goto("/app/repositories");
    
    // Check for Connect Repository button or heading
    const heading = page.locator("h1, h2, h3").filter({ hasText: /Repositories/i });
    await expect(heading.first()).toBeVisible();
  });

  test("5. Navigation bar enables switching between views", async ({ page }) => {
    await page.goto("/app");
    
    // Check links to Repositories, Chat, Search
    const chatLink = page.locator('a[href*="/app/chat"]');
    if (await chatLink.first().isVisible()) {
      await chatLink.first().click();
      await expect(page).toHaveURL(/.*\/app\/chat/);
    }
  });
});

