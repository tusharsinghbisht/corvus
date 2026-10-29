import { test, expect, Page } from "@playwright/test";

// Browser-only layout fixtures. No records are inserted or served by the product.
async function workspace(page: Page) {
  const now = new Date().toISOString();
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown;
    if (path === "/api/auth/me") json = { username: "ui-test" };
    else if (path === "/api/connections")
      json = {
        indexer_hosts: ["indexer.example"],
        connections: [
          {
            id: "00000000-0000-4000-8000-000000000001",
            name: "Layout fixture",
            indexer_url: "https://indexer.example:9200",
            username: "reader",
            enabled: true,
            backfill_start: now,
            checkpoint: now,
            last_sync_at: now,
            last_error: null,
          },
        ],
      };
    else if (path === "/api/alerts")
      json = {
        alerts: [
          {
            id: "00000000-0000-4000-8000-000000000002",
            connection_id: "00000000-0000-4000-8000-000000000001",
            timestamp: now,
            received_at: now,
            agent_id: "001",
            agent_name: "ui-test-host",
            rule_id: "100001",
            rule_level: 12,
            title: "UI layout fixture",
            native_id: "layout-fixture",
            native_index: "wazuh-alerts-ui-test",
          },
        ],
        stats: { total: 1, high: 1, agents: 1 },
        next_cursor: null,
      };
    else
      return route.fulfill({
        status: 404,
        json: { detail: "Not a layout fixture route" },
      });
    await route.fulfill({ json });
  });
  await page.goto("/soc");
  await expect(page.locator(".alert-title")).toHaveCount(1);
  await page.evaluate(() => document.fonts.ready);
}

test("floating rounded black panels and persistent collapsible navigation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.name));
  await workspace(page);
  const sidebar = page.locator("#workspace-sidebar");
  const main = page.locator(".soc-main");
  const original = await main.boundingBox();
  expect((await sidebar.boundingBox())!.x).toBeGreaterThan(0);
  expect((await sidebar.boundingBox())!.y).toBeGreaterThan(0);
  expect(
    parseFloat(
      await main.evaluate((node) => getComputedStyle(node).borderTopLeftRadius),
    ),
  ).toBeGreaterThanOrEqual(20);
  for (const selector of [".soc", ".sidebar", ".soc-main"]) {
    const color = await page
      .locator(selector)
      .evaluate((node) => getComputedStyle(node).backgroundColor);
    const channels = color.match(/[\d.]+/g)!.slice(0, 3);
    expect(channels[0]).toBe(channels[1]);
    expect(channels[1]).toBe(channels[2]);
  }
  await expect(page.locator("h1")).toHaveCSS("font-family", /bricolage/i);
  await expect(page.locator(".topbar")).toHaveCSS("font-family", /inter/i);
  await page.screenshot({
    path: "../artifacts/browser-tests/workspace-black.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(
    page.getByRole("button", { name: "Expand sidebar" }),
  ).toHaveAttribute("aria-expanded", "false");
  await expect
    .poll(async () => (await main.boundingBox())!.width)
    .toBeGreaterThan(original!.width + 100);
  expect(
    await page.evaluate(() => localStorage.getItem("corvus.sidebar.collapsed")),
  ).toBe("true");
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Expand sidebar" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Connections", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Connections", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Connections", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "Expand sidebar" }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", { name: "Collapse sidebar" }),
  ).toHaveAttribute("aria-expanded", "true");
  expect(errors).toEqual([]);
});

test("mobile margins, curved workspace, and sidebar disclosure", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await workspace(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.locator("#workspace-sidebar")).toBeHidden();
  await page.getByRole("button", { name: "Expand sidebar" }).click();
  await expect(page.locator("#workspace-sidebar")).toBeVisible();
  await page.screenshot({
    path: "../artifacts/browser-tests/workspace-mobile-black.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
