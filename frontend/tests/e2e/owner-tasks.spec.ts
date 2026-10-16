import { expect, test, type Page } from "@playwright/test";

/**
 * E6 — owner tasks (docs/v2/SPEC.md §5). An owner opens the app and finds, without scrolling:
 *   "did the cash balance?" · "what is my biggest money leak?" · "when is the next bill?"
 * at 390 px and 1440 px, with no console error and no "—" standing in for a number that exists.
 */
const PASSWORD = "E6-Passw0rd!x";

async function signIn(page: Page, restaurant: string) {
  await page.goto("/login");
  await page.fill("#restaurant-name", restaurant);
  await page.fill("#password", PASSWORD);
  await page.keyboard.press("Enter");
  await page.waitForURL("**/home", { timeout: 30_000 });
}

function watch(page: Page) {
  const problems: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text().slice(0, 200)}`); });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("response", (r) => { if (r.status() >= 500) problems.push(`${r.status()} ${r.url()}`); });
  return problems;
}

async function onFirstScreen(page: Page, answer: "cash" | "leak" | "bill") {
  const el = page.locator(`[data-answer=${answer}]`);
  await expect(el).toBeVisible();
  const box = (await el.boundingBox())!;
  const viewport = page.viewportSize()!;
  expect(box.y, `${answer} starts on screen`).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height, `${answer} ends within the first screen (${viewport.height}px)`).toBeLessThanOrEqual(viewport.height);
  return el;
}

test.describe("the owner of a restaurant with a history", () => {
  test.beforeEach(async ({ page }) => { await signIn(page, "Demo Restaurant"); await page.waitForSelector("[data-testid=sales-today]"); });

  test("did the cash balance? — on the first screen, with the number of counts", async ({ page }) => {
    const el = await onFirstScreen(page, "cash");
    await expect(el).toContainText(/\d+ counts?/);
  });

  test("what is my biggest money leak? — on the first screen, in shillings a month", async ({ page }) => {
    const el = await onFirstScreen(page, "leak");
    await expect(el).toContainText(/KES [\d,]+ a month/);
  });

  test("when is the next bill? — on the first screen, with the amount and the day", async ({ page }) => {
    const el = await onFirstScreen(page, "bill");
    await expect(el).toContainText(/KES [\d,]+ (today|in \d+ days?)/);
  });

  test("tapping an answer goes to its detail", async ({ page }) => {
    await page.locator("[data-answer=cash]").click();
    await expect(page).toHaveURL(/#area-cash$/);
    await expect(page.getByRole("region", { name: "Cash count check" })).toBeVisible();
  });

  test("Home, an area, Ask LEVIII and Reports open with no console error and no failed request", async ({ page }) => {
    const problems = watch(page);
    await page.reload();
    await page.waitForSelector("[data-testid=sales-today]");
    await page.getByRole("button", { name: /My Money/ }).click();
    await expect(page.getByRole("region", { name: "Profit & Loss" })).toBeVisible();
    await page.goto("/os");
    await expect(page.getByRole("navigation", { name: "Owner pages" }).first()).toBeVisible();
    await page.goto("/reports");
    await expect(page.getByRole("navigation", { name: "Owner pages" }).first()).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("no dash stands in for a number that exists", async ({ page }) => {
    for (const area of ["My Money", "Sales & Dishes", "Store & Suppliers", "Cash Check", "Staff", "Permits & Settings"]) await page.getByRole("button", { name: new RegExp(area) }).click();
    const dashes = await page.evaluate(() => [...document.querySelectorAll("main *")].filter((e) => e.children.length === 0 && e.textContent?.trim() === "—").map((e) => e.parentElement?.textContent?.slice(0, 80)));
    expect(dashes).toEqual([]);
  });

  test("there is no sideways scroll at this width", async ({ page }) => {
    for (const area of ["My Money", "Sales & Dishes", "Cash Check"]) await page.getByRole("button", { name: new RegExp(area) }).click();
    const [scroll, client] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    expect(scroll).toBeLessThanOrEqual(client);
  });

  test("every button, link and fold on Home is a comfortable tap target (40 px tall)", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "phone-390", "a phone is where a thumb has to hit it");
    for (const area of ["My Money", "Sales & Dishes", "Store & Suppliers", "Cash Check", "Staff", "Permits & Settings"]) await page.getByRole("button", { name: new RegExp(area) }).click();
    const small = await page.evaluate(() => [...document.querySelectorAll("a, button, summary")]
      .filter((e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.height < 39.5; })
      .map((e) => `${e.tagName} "${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 40)}" ${Math.round(e.getBoundingClientRect().height)}px`));
    expect(small).toEqual([]);
  });

  test("old addresses still land on the new Home", async ({ page }) => {
    await page.goto("/vibanda/stock");
    await expect(page).toHaveURL(/\/home#area-store$/);
    await page.goto("/demo");
    await expect(page).toHaveURL(/\/home$/);
  });
});

test.describe("the owner of a brand-new restaurant", () => {
  test("is asked for their targets, sees one panel and honest empty answers on the first screen", async ({ page }) => {
    const problems = watch(page);
    await signIn(page, "New Kitchen");
    await expect(page.getByRole("heading", { name: "Set your targets" })).toBeVisible();
    await expect(page.getByText(/day 1 of 6/)).toBeVisible();
    for (const answer of ["cash", "leak", "bill"] as const) await expect(page.locator(`[data-answer=${answer}]`)).toBeVisible();
    await expect(page.locator("[data-answer=bill]")).toContainText(/No bills/);
    await expect(page.getByRole("region", { name: /My Money, opens on day 2/ })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("can set targets and see that Home asks again", async ({ page }, testInfo) => {
    await signIn(page, testInfo.project.name === "phone-390" ? "Targets Phone" : "Targets Desk");     // saving changes the restaurant, so each size has its own
    await page.getByRole("button", { name: "Set my targets" }).click();
    const dialog = page.getByRole("dialog", { name: "Your targets" });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "These are right" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("heading", { name: "Set your targets" })).toBeHidden();
  });
});
