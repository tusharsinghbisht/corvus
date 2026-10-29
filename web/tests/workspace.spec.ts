import { test, expect, Page } from "@playwright/test";

test.skip(
  !process.env.CORVUS_TEST_DATABASE_URL,
  "Workspace integration tests require a disposable PostgreSQL database",
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

test("private APIs reject anonymous requests and the workspace redirects to login", async ({
  page,
  request,
}) => {
  expect((await request.get("/api/alerts")).status()).toBe(401);
  await page.goto("/soc");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(5, 5, 5)",
  );
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

test("manual triage requires bundle approval and preserves report and failed candidate history", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("searchbox", { name: "Search alerts" }).fill("<img");
  await page.locator(".alert-title").click();
  const investigation = page.getByRole("region", {
    name: "Manual Analyst investigation",
  });
  await investigation
    .getByRole("button", { name: "Collect evidence", exact: true })
    .click();
  await expect(investigation.getByRole("status")).toContainText(
    "Awaiting your approval",
    { timeout: 90000 },
  );
  const approve = investigation.getByRole("button", {
    name: "Approve one Analyst request",
  });
  await expect(approve).toBeDisabled();
  await investigation
    .getByText("Inspect exact evidence selected for external processing", {
      exact: true,
    })
    .click();
  await expect(investigation.locator(".saved-evidence pre")).toContainText(
    "evidence_digest",
  );
  await expect(investigation.locator(".saved-evidence pre")).toContainText(
    "untrusted DATA",
  );
  await investigation.getByRole("checkbox").check();
  await page.reload();
  await expect(approve).toBeDisabled();
  await investigation.getByRole("checkbox").check();
  await approve.click();
  await expect(
    investigation.getByRole("heading", { name: "Findings", exact: true }),
  ).toBeVisible({ timeout: 90000 });
  await expect(investigation.getByRole("status")).toContainText(
    "human review required",
  );
  await expect(investigation.locator(".investigation-report")).toContainText(
    "<img src=x",
  );
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  expect(
    await page.evaluate(
      () => (window as unknown as Record<string, unknown>).corvusInjection,
    ),
  ).toBeUndefined();
  await investigation.locator(".citations summary").first().click();
  await expect(investigation.locator(".citations pre").first()).toContainText(
    "reference",
  );
  await investigation
    .getByText("Attempt provenance and approval record", { exact: true })
    .click();
  await expect(investigation.locator("pre").last()).toContainText(
    "approved_digest",
  );
  await investigation
    .getByRole("button", { name: "Collect new attempt" })
    .click();
  await expect(investigation.getByRole("status")).toContainText(
    "Awaiting your approval",
    { timeout: 90000 },
  );
  await investigation.getByRole("checkbox").check();
  await approve.click();
  await expect(investigation.getByRole("status")).toContainText(
    "Candidate rejected",
    { timeout: 90000 },
  );
  await expect(
    investigation.getByRole("heading", { name: "Findings", exact: true }),
  ).toHaveCount(0);
  await investigation
    .getByText("Original model reply · untrusted text", { exact: true })
    .click();
  await expect(
    investigation
      .locator("pre")
      .filter({ hasText: "invalid candidate" })
      .last(),
  ).toContainText("<script>untrusted</script>");
  await investigation.getByLabel("Attempt history").selectOption({ index: 1 });
  await expect(
    investigation.getByRole("heading", { name: "Findings", exact: true }),
  ).toBeVisible();
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
