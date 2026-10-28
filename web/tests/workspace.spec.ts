import { test, expect, Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username", { exact: true }).fill("test-admin");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-only-password-not-a-secret");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Alert queue" }),
  ).toBeVisible();
}

test("public landing page has the custom mark and private APIs reject anonymous requests", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "More context. Fewer assumptions." }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator(".brand svg")
        .first()
        .evaluate((node) => (node as SVGGraphicsElement).getBBox().width),
    )
    .toBeGreaterThan(0);
  await page.screenshot({
    path: "../artifacts/browser-tests/landing.png",
    fullPage: true,
  });
  expect((await request.get("/api/alerts")).status()).toBe(401);
  await page.goto("/soc");
  await expect(page).toHaveURL(/\/login$/);
});

test("alert pagination, filtering, source inspection, and untrusted markup", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);
  await expect(page.locator(".alert-title")).toHaveCount(50);
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page.locator(".alert-title")).toHaveCount(5);
  await page.getByRole("button", { name: "Previous page" }).click();
  await expect(page.locator(".alert-title")).toHaveCount(50);
  await page.getByLabel("Minimum severity").selectOption("12");
  await expect(page.locator(".alert-title")).toHaveCount(3);
  await page.getByLabel("Minimum severity").selectOption("0");
  await page.getByRole("searchbox", { name: "Search alerts" }).fill("<img");
  await expect(page.locator(".alert-title")).toHaveCount(1);
  await page.locator(".alert-title").click();
  await expect(
    page.getByRole("heading", { name: "Event context" }),
  ).toBeVisible();
  await page.locator("summary").click();
  await expect(page.locator("pre")).toContainText("onerror=");
  expect(
    await page.evaluate(
      () => (window as unknown as Record<string, unknown>).corvusInjection,
    ),
  ).toBeUndefined();
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("connection controls and logout", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Connections", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Browser-test Wazuh" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pause ingestion" }).click();
  await expect(page.locator(".connection-status")).toContainText("Paused");
  await page.getByRole("button", { name: "Resume ingestion" }).click();
  await expect(
    page.getByRole("button", { name: "Pause ingestion" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Connect Wazuh", exact: true })
    .click();
  await expect(page.getByLabel("Read-only password")).toHaveAttribute(
    "type",
    "password",
  );
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test("mobile workspace stays within the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await expect(page.locator(".alert-title")).toHaveCount(50);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../artifacts/browser-tests/mobile.png",
    fullPage: true,
  });
});
