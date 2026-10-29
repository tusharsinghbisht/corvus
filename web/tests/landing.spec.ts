import { test, expect } from "@playwright/test";

test("black theme, self-hosted font pair, isometric controls, and glass buttons", async ({
  page,
}) => {
  const errors: string[] = [];
  const external: string[] = [];
  page.on("pageerror", (error) => errors.push(error.name));
  page.on("request", (request) => {
    if (!request.url().startsWith("http://127.0.0.1:8768/"))
      external.push(request.url());
  });
  await page.goto("/");
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(5, 5, 5)",
  );
  await expect(page.locator("body")).toHaveCSS("font-family", /inter/i);
  await expect(page.locator("h1")).toHaveCSS("font-family", /bricolage/i);
  await expect(page.locator(".hero-actions .button")).toHaveCSS(
    "background-image",
    /linear-gradient/,
  );
  await page
    .locator(".scene-controls button")
    .filter({ hasText: "PostgreSQL" })
    .click();
  await expect(page.locator(".scene-description")).toContainText(
    "The durable record",
  );
  await page
    .locator(".scene-controls button")
    .filter({ hasText: "Wazuh" })
    .click();
  await expect(page.locator(".scene-description")).toContainText(
    "read-only account",
  );
  await page.screenshot({
    path: "../artifacts/browser-tests/landing-black.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test("multi-agent architecture, planned orchestration, and FAQ disclosure", async ({
  page,
}) => {
  const apiRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/"))
      apiRequests.push(request.url());
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Analyst pipeline", exact: true })
    .click();
  await page
    .locator(".architecture-step button")
    .filter({ hasText: "Analyze" })
    .click();
  await expect(page.locator(".architecture-detail")).toContainText(
    "model-provider interface",
  );
  await expect(page.locator("#stack .tech-card")).toHaveCount(5);
  await expect(page.locator(".tech-card-planned")).toContainText("LangGraph");
  await expect(page.locator(".tech-card-planned")).toContainText("Planned");
  await expect(page.locator("#stack")).not.toContainText("Azure");
  await expect(page.locator("#stack")).not.toContainText("DeepSeek");
  await page
    .getByRole("button", { name: "Live ingestion", exact: true })
    .click();
  await page
    .locator(".architecture-step button")
    .filter({ hasText: "PostgreSQL" })
    .click();
  await expect(page.locator(".architecture-detail")).toContainText("JSONB");
  await page
    .locator(".agent-map button")
    .filter({ hasText: "Intel agent" })
    .click();
  await expect(page.locator(".agent-details")).toContainText("Planned");
  await expect(page.locator(".agent-details")).toContainText("Analyst");
  await page
    .locator(".agent-map button")
    .filter({ hasText: "Containment agent" })
    .click();
  await expect(page.locator(".agent-details")).toContainText("approved plan");
  await expect(
    page.getByText("THE NEXT LAYER: ANALYST IN YOUR QUEUE", { exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".landing")).not.toContainText("Azure");
  await expect(page.locator(".landing")).not.toContainText("DeepSeek");
  await page
    .locator(".faq-list summary")
    .filter({ hasText: "Does Corvus replace Wazuh?" })
    .click();
  await expect(page.locator(".faq-list details").first()).toHaveAttribute(
    "open",
    "",
  );
  expect(apiRequests).toEqual([]);
});

test("mobile landing and login fit the viewport and respect reduced motion", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const duration = await page
    .locator(".scene-signal")
    .evaluate((node) => parseFloat(getComputedStyle(node).animationDuration));
  expect(duration).toBeLessThan(0.01);
  await page.screenshot({
    path: "../artifacts/browser-tests/landing-mobile-black.png",
    fullPage: true,
  });
  await page.goto("/login");
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(5, 5, 5)",
  );
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute(
    "type",
    "password",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
