import { test, expect, Page } from "@playwright/test";

test.skip(
  !process.env.CORVUS_TEST_DATABASE_URL,
  "Workspace tests require disposable PostgreSQL",
);
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

test("private APIs reject anonymous access", async ({ page, request }) => {
  for (const path of [
    "/api/alerts",
    "/api/settings/analyst",
    "/api/agents/analyst",
  ])
    expect((await request.get(path)).status()).toBe(401);
  await page.goto("/soc");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(5, 5, 5)",
  );
});

test("alert pagination, filters, and untrusted source inspection", async ({
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
  await page.locator(".alert-title").click();
  await expect(
    page.getByRole("heading", { name: "Event context" }),
  ).toBeVisible();
  await page.locator(".source-panel summary").click();
  await expect(page.locator(".source-panel pre")).toContainText("onerror=");
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  expect(
    await page.evaluate(
      () => (window as unknown as Record<string, unknown>).corvusInjection,
    ),
  ).toBeUndefined();
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

test("Analyst report, interactive evidence map, approval, and preserved failure history", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("searchbox", { name: "Search alerts" }).fill("<img");
  await page.locator(".alert-title").click();
  const investigation = page.getByRole("region", {
    name: "Analyst investigation",
    exact: true,
  });
  const investigate = investigation.getByRole("button", {
    name: "Investigate with Analyst",
    exact: true,
  });
  const approve = investigation.getByRole("button", {
    name: "Approve one Analyst request",
  });
  await investigate.click();
  await expect(investigation.getByRole("status")).toContainText(
    "Awaiting your approval",
  );
  await expect(approve).toBeDisabled();
  await investigation
    .getByText("Review evidence selected for Analyst", { exact: true })
    .click();
  await expect(investigation.locator(".saved-evidence")).toContainText(
    "Triggering alert",
  );
  await investigation.getByRole("checkbox").check();
  await page.reload();
  await expect(approve).toBeDisabled();
  await investigation.getByRole("checkbox").check();
  await approve.click();
  await expect(
    investigation.getByRole("heading", { name: "Findings", exact: true }),
  ).toBeVisible();
  await expect(investigation.getByRole("status")).toContainText(
    "human review required",
  );
  await expect(investigation.locator("pre:visible")).toHaveCount(0);
  await expect(investigation.locator(".investigation-report")).toContainText(
    "<img src=x",
  );
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  const map = investigation.getByRole("region", {
    name: "Interactive evidence map",
  });
  await map.getByRole("button", { name: /^Finding F/ }).click();
  await map
    .getByRole("button", { name: /^Open evidence/ })
    .first()
    .click();
  await expect(
    map.locator(".map-inspector .evidence-facts").first(),
  ).toBeVisible();
  await expect(map.locator("pre")).toHaveCount(0);
  await investigation.locator(".citations summary").first().click();
  await expect(
    investigation.locator(".citations .evidence-facts").first(),
  ).toBeVisible();
  // Rejected candidates are preserved, but are never presented as a report.
  await investigate.click();
  await expect(investigation.getByRole("status")).toContainText(
    "Awaiting your approval",
  );
  await investigation.getByRole("checkbox").check();
  await approve.click();
  await expect(investigation.getByRole("status")).toContainText(
    "Candidate rejected",
  );
  await expect(
    investigation.getByRole("heading", { name: "Findings", exact: true }),
  ).toHaveCount(0);
  await investigation
    .getByText("Technical record · provenance, original replies, and JSON", {
      exact: true,
    })
    .click();
  await investigation
    .getByText("Original model reply · untrusted text", { exact: true })
    .click();
  await expect(investigation.locator("pre:visible")).toContainText(
    "invalid candidate",
  );
  // Reload defaults to the last valid report, not the newest failed attempt.
  await page.reload();
  await expect(
    investigation.getByRole("heading", { name: "Findings", exact: true }),
  ).toBeVisible();
  await expect(investigation.locator("pre:visible")).toHaveCount(0);
  await investigate.click();
  await expect(investigation.getByRole("status")).toContainText(
    "Awaiting your approval",
  );
  await investigation.getByRole("checkbox").check();
  await approve.click();
  await expect(investigation.getByRole("alert")).toContainText(
    "reached the configured output-token limit",
  );
  await expect(investigation.getByRole("alert")).toContainText("4,096 / 4,096");
  await expect(investigation.getByRole("alert")).toContainText(
    "Finish reason: length",
  );
  await investigate.click();
  await expect(investigation.getByRole("status")).toContainText(
    "Awaiting your approval",
  );
  await investigation.getByRole("checkbox").check();
  await approve.click();
  await expect(investigation.getByRole("alert")).toContainText(
    "original finish reason was not recorded",
  );
  await expect(investigation.getByRole("alert")).not.toContainText(
    "Finish reason: length",
  );
  await page.reload();
  await expect(
    investigation.getByRole("heading", { name: "Findings", exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await map.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "../artifacts/browser-tests/analyst-evidence-map-mobile.png",
  });
});

test("Settings policies require explicit consent and the Analyst navigation is operational", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Settings", exact: true }),
  ).toBeVisible();
  const card = page.getByRole("region", {
    name: "Analyst policy for Browser-test Wazuh",
  });
  await card.getByRole("button", { name: "Automatic", exact: true }).click();
  await card
    .getByLabel("Minimum severity for Browser-test Wazuh")
    .selectOption("15");
  await card
    .getByLabel("Hourly request limit for Browser-test Wazuh")
    .fill("1");
  await card.getByLabel("Daily request limit for Browser-test Wazuh").fill("2");
  const save = card.getByRole("button", { name: "Save automatic policy" });
  await expect(save).toBeDisabled();
  await card.getByRole("checkbox").check();
  await save.click();
  await expect(card).toContainText("Last consent:");
  await page.reload();
  await expect(
    card.getByRole("button", { name: "Automatic", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await card.getByRole("button", { name: "Manual", exact: true }).click();
  await card.getByRole("button", { name: "Use manual mode" }).click();
  await expect(
    card.getByRole("button", { name: "Manual", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    card.getByRole("button", { name: "Use manual mode" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await expect(page.locator(".planned-agent")).toHaveCount(4);
  await page.getByRole("link", { name: "Analyst Active" }).click();
  await expect(
    page.getByRole("heading", { name: "Analyst", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Recent investigations" }),
  ).toBeVisible();
  await expect(page.locator(".alert-title").first()).toBeVisible();
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
});
