import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

/**
 * E6 — owner tasks (docs/v2/SPEC.md §5). An owner opens the app and finds, without scrolling:
 *   "did the cash balance?" · "what is my biggest money leak?" · "when is the next bill?"
 * at 390 px and 1440 px, with no console error and no "—" standing in for a number that exists.
 */
const PASSWORD = "E6-Passw0rd!x";

/** The Nairobi day the test database was built on (execution/e6_backend.py) and today's. They differ when a run crosses Nairobi midnight. */
const builtOn = () => { try { return readFileSync(path.resolve(process.cwd(), "..", ".tmp", "e6", "built_on.txt"), "utf8").trim(); } catch { return ""; } };
const nairobiToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Nairobi" }).format(new Date());

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

  test("did the M-Pesa money arrive? — Home and the cash panel name the three sales the statement never shows", async ({ page }) => {
    const sentence = /3 M-Pesa sales \(KES [\d,]+\) have no payment on your statement\./;
    await expect(page.getByText(sentence).first()).toBeVisible();                                         // Zone 1
    await page.getByRole("button", { name: /Cash Check/ }).click();
    const panel = page.getByRole("region", { name: "M-Pesa check" });
    await expect(panel).toBeVisible();
    await expect(panel).toContainText(sentence);
    await expect(panel).toContainText("From your M-Pesa statement");
    await expect(panel.getByText(/^Sales with no payment on the statement · KES [\d,]+$/)).toBeVisible();
    await expect(panel.getByRole("listitem").filter({ hasText: /Table \d+|Takeaway or delivery/ })).toHaveCount(3);
  });

  test("a statement can be uploaded, the rows it could not read are listed, and the upload can be taken back", async ({ page }) => {
    const problems = watch(page);
    await page.getByRole("button", { name: /Cash Check/ }).click();
    const upload = page.getByRole("region", { name: "Your M-Pesa statement" });
    await expect(upload).toBeVisible();
    // Money going out is not a payment to explain, and a row without a time is left out and listed: the check itself does not move.
    const csv = ["Receipt No.,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance",
      "E6OUT00001,2026-09-01 10:00:00,Business Payment to E6 SUPPLIER,Completed,,\"1,200.00\",",
      "E6BAD00001,not a time,Customer Payment,Completed,50.00,,"].join("\n");
    await upload.locator("input[type=file]").setInputFiles({ name: "e6-statement.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
    const status = upload.getByRole("status");
    await expect(status).toContainText("Read 1 new payment from e6-statement.csv", { timeout: 30_000 });
    await expect(status).toContainText("1 row was not read");
    await status.getByText("1 row was not read").click();
    await expect(status).toContainText("Row 3: the time 'not a time' is not one we can read");
    await expect(page.getByRole("region", { name: "M-Pesa check" })).toContainText(/3 M-Pesa sales/);        // unchanged
    await upload.getByText(/payments? on file from \d+ uploads?/).click();           // the demo's own statement is on file too: take back only this one
    const mine = upload.getByRole("listitem").filter({ hasText: "e6-statement.csv" });
    await expect(mine).toHaveCount(1);
    await mine.getByRole("button", { name: "Remove this upload" }).click();
    await expect(mine).toHaveCount(0, { timeout: 30_000 });
    await expect(page.getByRole("region", { name: "M-Pesa check" })).toContainText(/3 M-Pesa sales/);        // and the check is as it was
    expect(problems).toEqual([]);
  });

  test("Ask LEVIII answers in five ways, each from the owner's own records", async ({ page }) => {
    const problems = watch(page);
    await page.goto("/os");
    const asks: [string, string, RegExp][] = [
      ["What should I do to make more money?", "what_to_do", /KES [\d,]+/],
      ["What if I raise the price of Chips to 350?", "what_if", /Worth trying|Be careful|Not worth it/],
      ["Compare my branches", "compare", /Kasarani/],
      ["Am I making a profit this month?", "what", /you sold KES [\d,]+/],
      ["Do my M-Pesa payments match my sales?", "what", /3 M-Pesa sales \(KES [\d,]+\) have no payment on your statement/],
    ];
    for (const [question, form, expected] of asks) {
      await page.getByLabel("Ask or describe a change").fill(question);
      await page.getByRole("button", { name: "Send question" }).click();
      const card = page.locator(`[data-form=${form}]`).last();
      await expect(card, question).toBeVisible({ timeout: 30_000 });
      await expect(card, question).toContainText(expected);
      await expect(card).not.toContainText(/planned|not available yet/i);
    }
    expect(problems).toEqual([]);
  });

  test("Ask LEVIII has no sideways scroll, and every button on it is a comfortable tap target", async ({ page }, testInfo) => {
    await page.goto("/os");
    await page.getByRole("radio", { name: "Why" }).click();
    const [scroll, client] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    expect(scroll).toBeLessThanOrEqual(client);
    test.skip(testInfo.project.name !== "phone-390", "a phone is where a thumb has to hit it");
    const small = await page.evaluate(() => [...document.querySelectorAll("main a, main button, main summary")]
      .filter((e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.height < 39.5; })
      .map((e) => `${e.tagName} "${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 40)}" ${Math.round(e.getBoundingClientRect().height)}px`));
    expect(small).toEqual([]);
  });

  test("the four reports open, each with its own sections and nothing marked as planned", async ({ page }) => {
    const problems = watch(page);
    await page.goto("/reports");
    const expected: [string, string[]][] = [
      ["Daily", ["Sales", "Cash count check", "Things to check", "Stock today"]],
      ["Weekly", ["Best and weakest dishes", "Price ideas", "Missing stock", "Wages", "Suppliers"]],
      ["Monthly", ["Profit & Loss", "Costs", "Delivery apps and dine-in", "What cost you money", "Targets used in this report"]],
      ["Yearly", ["Trends", "Profit & Loss by month", "Busy and quiet months"]],
    ];
    for (const [tab, sections] of expected) {
      await page.getByRole("tab", { name: tab }).click();
      for (const title of sections) await expect(page.getByRole("region", { name: title }).first(), `${tab}: ${title}`).toBeVisible({ timeout: 30_000 });
      await expect(page.locator("main")).not.toContainText(/planned|not available yet/i);
    }
    expect(problems).toEqual([]);
  });

  test("the monthly report can be read for a past month, and the accountant's file is offered", async ({ page }) => {
    await page.goto("/reports");
    await page.getByRole("tab", { name: "Monthly" }).click();
    await expect(page.getByRole("region", { name: "Profit & Loss" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: /Excel/ })).toBeVisible();
    const select = page.getByLabel("Month");
    const labels = await select.locator("option").allTextContents();
    expect(labels).toHaveLength(12);
    await select.selectOption({ index: 1 });
    await expect(page.getByText(`monthly · ${labels[1].replace(" (so far)", "")}`, { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("region", { name: "Sales" })).not.toContainText(/so far/i, { timeout: 30_000 });      // a month that is over is not "so far"
  });

  test("Reports has no sideways scroll, and every button on it is a comfortable tap target", async ({ page }, testInfo) => {
    await page.goto("/reports");
    await page.getByRole("tab", { name: "Weekly" }).click();
    await expect(page.getByRole("region", { name: "Suppliers" })).toBeVisible({ timeout: 30_000 });
    const [scroll, client] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    expect(scroll).toBeLessThanOrEqual(client);
    test.skip(testInfo.project.name !== "phone-390", "a phone is where a thumb has to hit it");
    const small = await page.evaluate(() => [...document.querySelectorAll("main a, main button, main summary, main select, main [role=tab]")]
      .filter((e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.height < 39.5; })
      .map((e) => `${e.tagName} "${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 40)}" ${Math.round(e.getBoundingClientRect().height)}px`));
    expect(small).toEqual([]);
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
    test.skip(builtOn() !== nairobiToday(), "this run crossed Nairobi midnight, so a restaurant created at its start is on day 2, not day 1");
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
