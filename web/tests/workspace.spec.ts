import { test, expect, Page } from "@playwright/test";
import { readFile } from "node:fs/promises";

test.skip(
  !process.env.CORVUS_TEST_DATABASE_URL,
  "Workspace tests require disposable PostgreSQL",
);
function observeUiErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.name));
  page.on("console", (message) => {
    // Expected authentication/conflict HTTP responses are asserted separately.
    if (
      message.type() === "error" &&
      !message.text().startsWith("Failed to load resource")
    )
      errors.push(message.text());
  });
  return errors;
}
const uiErrors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  uiErrors.set(page, observeUiErrors(page));
});
test.afterEach(async ({ page }) => {
  expect(uiErrors.get(page) ?? []).toEqual([]);
});

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
    "/api/operations",
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
  await expect(page.locator(".alert-title")).toHaveCount(1);
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
  await expect(page.locator(".alert-title")).toHaveCount(1);
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
  const focused = investigation.getByRole("button", {
    name: "Focused · up to 4 events / 16 KiB",
    exact: true,
  });
  const broader = investigation.getByRole("button", {
    name: "Broader · up to 12 events / 48 KiB",
    exact: true,
  });
  await expect(focused).toHaveAttribute("aria-pressed", "true");
  await investigation.getByRole("checkbox").check();
  await broader.click();
  await expect(broader).toHaveAttribute("aria-pressed", "true");
  await expect(investigation.getByRole("checkbox")).not.toBeChecked();
  await expect(approve).toBeDisabled();
  await focused.click();
  await expect(focused).toHaveAttribute("aria-pressed", "true");
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
  await expect(
    investigation.locator(".report-label .review-badge"),
  ).toContainText("Human review required");
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
  await expect(
    investigation.getByRole("region", {
      name: "Report integrity issues",
      exact: true,
    }),
  ).toContainText("Nothing is repaired or retried automatically");
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

test("human review is evidence-bound, survives reload, handles stale tabs, and updates queues", async ({
  page,
  context,
}) => {
  await login(page);
  const started: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      (/\/investigations$/.test(new URL(request.url()).pathname) ||
        request.url().endsWith("/approve"))
    )
      started.push(request.url());
  });
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await page.getByRole("link", { name: "Analyst Active" }).click();
  await page.getByLabel("Human review filter").selectOption("all");
  await expect(page.locator(".alert-title").first()).toBeVisible();
  // The newest attempt failed. Its deep link must not silently open an older report.
  await page.locator(".alert-title").first().click();
  await expect(page.locator(".attempt-status")).toContainText("Attempt failed");
  await expect(
    page.getByRole("heading", { name: "Findings", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "Analyst Active" }).click();
  await page.getByLabel("Human review filter").selectOption("pending");
  await expect(page.locator(".alert-title")).toHaveCount(1);
  await page.locator(".alert-title").click();
  await expect(page).toHaveURL(/\?attempt=/);
  const review = page.getByRole("region", { name: "Human assessment review" });
  await expect(
    review.getByRole("heading", { name: "Human review", exact: true }),
  ).toBeVisible();
  const peer = await context.newPage();
  const peerErrors = observeUiErrors(peer);
  await peer.goto(page.url());
  const peerReview = peer.getByRole("region", {
    name: "Human assessment review",
  });
  await expect(
    peerReview.locator(".review-heading .review-badge"),
  ).toContainText("Human review required");
  await review
    .getByRole("radio", { name: "Accept assessment", exact: true })
    .check();
  const note =
    'Checked the source facts and alternatives. <img src=x onerror="window.corvusReviewInjection=true">';
  await review.getByLabel("Review rationale", { exact: true }).fill(note);
  const save = review.getByRole("button", {
    name: "Save human review",
    exact: true,
  });
  await expect(save).toBeDisabled();
  await review.getByRole("checkbox").check();
  await save.click();
  await expect(review.getByRole("status")).toContainText(
    "Human review recorded",
  );
  await expect(review.locator(".review-heading .review-badge")).toContainText(
    "Assessment accepted",
  );
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  expect(
    await page.evaluate(
      () =>
        (window as unknown as Record<string, unknown>).corvusReviewInjection,
    ),
  ).toBeUndefined();
  // The other tab still targets review sequence zero. It must not overwrite acceptance.
  await peerReview
    .getByRole("radio", { name: "Needs follow-up", exact: true })
    .check();
  await peerReview
    .getByLabel("Review rationale", { exact: true })
    .fill("Need a fresh source check before relying on this assessment.");
  await peerReview
    .getByRole("button", { name: "Save human review", exact: true })
    .click();
  await expect(peerReview.getByRole("alert")).toContainText(
    "Review history changed",
  );
  await peerReview
    .getByRole("button", { name: "Reload report and review history" })
    .click();
  await expect(
    peerReview.locator(".review-heading .review-badge"),
  ).toContainText("Assessment accepted");
  await peerReview
    .getByRole("button", { name: "Save human review", exact: true })
    .click();
  await expect(
    peerReview.locator(".review-heading .review-badge"),
  ).toContainText("Follow-up needed");
  await peer.close();
  await page.reload();
  await expect(review.locator(".review-heading .review-badge")).toContainText(
    "Follow-up needed",
  );
  await review
    .getByText("Review history · 2 decisions", { exact: true })
    .click();
  await expect(review.locator(".review-history .review-entry")).toHaveCount(2);
  await expect(review.locator(".review-history")).toContainText(note);
  await review
    .getByRole("radio", { name: "Reject assessment", exact: true })
    .check();
  await review
    .getByLabel("Review rationale", { exact: true })
    .fill("The cited source does not establish the claimed conclusion.");
  await save.click();
  await expect(review.locator(".review-heading .review-badge")).toContainText(
    "Assessment rejected",
  );
  await expect(
    page.getByRole("heading", { name: "Findings", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(review.locator(".review-heading .review-badge")).toContainText(
    "Assessment rejected",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await review.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "../artifacts/browser-tests/human-review-mobile.png",
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await page.getByRole("searchbox", { name: "Search alerts" }).fill("<img");
  await expect(page.locator(".alert-title")).toHaveCount(1);
  await expect(page.locator(".investigation-cell")).toContainText(
    "Assessment rejected",
  );
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await page.getByRole("link", { name: "Analyst Active" }).click();
  await page.getByLabel("Human review filter").selectOption("rejected");
  await expect(page.locator(".alert-title")).toHaveCount(1);
  await expect(page.locator(".table-wrap")).toContainText(
    "Assessment rejected",
  );
  await page.getByLabel("Human review filter").selectOption("pending");
  await expect(page.locator(".alert-title")).toHaveCount(0);
  expect(started).toEqual([]);
  expect(peerErrors).toEqual([]);
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
  await expect(page.locator(".planned-agent")).toHaveCount(2);
  await page.getByRole("link", { name: "Analyst Active" }).click();
  await expect(
    page.getByRole("heading", { name: "Analyst", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Recent investigations" }),
  ).toBeVisible();
  await expect(page.locator(".table-wrap")).toBeVisible();
});

test("investigation queue filters and private handoffs never start another model request", async ({
  page,
}) => {
  const started: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().includes("/investigations")
    )
      started.push(request.url());
  });
  await login(page);
  const queue = page.getByLabel("Investigation queue", { exact: true });
  await queue.selectOption("reviewed");
  await expect(page.locator(".alert-title")).toHaveCount(1);
  await queue.selectOption("needs_review");
  await expect(page.locator(".alert-title")).toHaveCount(0);
  await queue.selectOption("attention");
  await expect(page.locator(".alert-title")).toHaveCount(1);
  await page.locator(".alert-title").click();
  const handoff = page.locator(".investigation-export");
  await handoff.locator("summary").click();
  const summary = handoff.getByRole("button", {
    name: "Download report summary",
    exact: true,
  });
  await expect(summary).toBeDisabled();
  await handoff.getByRole("checkbox").check();
  const markdownEvent = page.waitForEvent("download");
  await summary.click();
  const markdown = await markdownEvent;
  expect(markdown.suggestedFilename()).toMatch(/^corvus-investigation-.*\.md$/);
  const text = await readFile((await markdown.path())!, "utf8");
  expect(text).toContain("# Corvus investigation");
  expect(text).toContain("## Human review history");
  expect(text).not.toContain("<img");
  const zipEvent = page.waitForEvent("download");
  await handoff
    .getByRole("button", { name: "Download evidence package", exact: true })
    .click();
  const zip = await zipEvent;
  expect(zip.suggestedFilename()).toMatch(/^corvus-investigation-.*\.zip$/);
  expect((await readFile((await zip.path())!)).subarray(0, 2).toString()).toBe(
    "PK",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await handoff.scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../artifacts/browser-tests/investigation-handoff-mobile.png",
  });
  expect(started).toEqual([]);
});

test("Settings displays real readiness without administrative or model execution controls", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  const readiness = page.getByRole("region", {
    name: "Operational readiness",
    exact: true,
  });
  await expect(readiness).toContainText("Worker heartbeat");
  await expect(readiness).toContainText("Not configured");
  await expect(readiness).toContainText("Snapshots are local to this VM");
  await expect(readiness.getByRole("button")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await readiness.scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../artifacts/browser-tests/operational-readiness-mobile.png",
  });
});

test("local Correlation and Intel expose real saved inputs without another model request", async ({
  page,
}) => {
  const mutations: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().includes("/investigations")
    )
      mutations.push(request.url());
  });
  await login(page);
  await page.goto("/soc/agents/correlation");
  await expect(
    page.getByRole("heading", { name: "Correlation", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".alert-title").first()).toBeVisible();
  await page.locator(".alert-title").first().click();
  await expect(page).toHaveURL(/\?attempt=/);
  const local = page.locator(".local-agent-context");
  await local.locator("summary").first().click();
  await expect(
    local.getByRole("region", { name: "Correlation selection" }),
  ).toContainText("selection hints");
  await expect(
    local.getByRole("region", { name: "Local indicator intelligence" }),
  ).toContainText("No DNS");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("#agent-navigation")).toHaveCount(0);
  await local.scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../artifacts/browser-tests/local-agents-mobile.png",
  });
  await page.goto("/soc/agents/intel");
  await expect(
    page.getByRole("heading", { name: "Intel", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".alert-title").first()).toBeVisible();
  expect(mutations).toEqual([]);
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
