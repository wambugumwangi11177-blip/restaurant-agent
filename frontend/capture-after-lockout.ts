import { chromium } from 'playwright';
import type { Page } from 'playwright';
import * as path from 'path';

const BASE_URL = 'https://frontend-test-production-752b1b7c.up.railway.app';
const OUTPUT_DIR = '/opt/cursor/artifacts';

const OWNER_EMAIL = 'owner@eleven.leviii';
const JACK_EMAIL = 'jack@eleven.leviii';
const AMINA_EMAIL = 'amina@eleven.leviii';
const PASSWORD = 'NewPass2';

interface Screenshot {
  name: string;
  url: string;
  email: string;
  waitForSelector?: string;
}

const screenshots: Screenshot[] = [
  { name: 'owner-home', url: '/eleven', email: OWNER_EMAIL },
  { name: 'owner-dishes', url: '/eleven/dishes', email: OWNER_EMAIL },
  { name: 'owner-money', url: '/eleven/money', email: OWNER_EMAIL },
  { name: 'owner-alerts', url: '/eleven/alerts', email: OWNER_EMAIL },
  { name: 'owner-handover-timeline', url: '/eleven/handover', email: OWNER_EMAIL },
  { name: 'jack-wizard-step1', url: '/store', email: JACK_EMAIL },
  { name: 'jack-restock-whatsapp', url: '/store/requests', email: JACK_EMAIL },
  { name: 'store-prep-list', url: '/store/recipes', email: JACK_EMAIL },
  { name: 'accountant-invoice-prices', url: '/store', email: AMINA_EMAIL },
];

async function checkLockout(page: Page): Promise<number> {
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.locator('input[type="email"]').fill(OWNER_EMAIL);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(2000);
    
    const bodyText = await page.locator('body').textContent();
    const lockMatch = bodyText?.match(/Try again in (\d+) minute/);
    return lockMatch ? parseInt(lockMatch[1]) : 0;
  } catch (error) {
    return 0;
  }
}

async function login(page: Page, email: string): Promise<boolean> {
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(3000);
    
    const url = page.url();
    if (!url.includes('/login')) {
      console.log(`✓ Login successful for ${email}`);
      return true;
    }
    
    const bodyText = await page.locator('body').textContent() || '';
    if (bodyText.includes('locked')) {
      console.log(`⚠ Account still locked for ${email}`);
      return false;
    }
    
    console.log(`✗ Login failed for ${email}`);
    return false;
  } catch (error) {
    console.log(`✗ Login error for ${email}:`, error);
    return false;
  }
}

async function captureScreenshot(page: Page, screenshot: Screenshot): Promise<boolean> {
  try {
    console.log(`\nCapturing: ${screenshot.name}`);
    
    // Login if needed
    if (page.url().includes('/login') || !page.url().includes(BASE_URL)) {
      const success = await login(page, screenshot.email);
      if (!success) {
        await page.screenshot({ path: path.join(OUTPUT_DIR, `${screenshot.name}-login-failed.png`) });
        return false;
      }
    }
    
    // Navigate to target page
    await page.goto(`${BASE_URL}${screenshot.url}`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    
    // Capture screenshot
    const outputPath = path.join(OUTPUT_DIR, `${screenshot.name}.png`);
    await page.screenshot({ path: outputPath });
    console.log(`✓ Saved: ${outputPath}`);
    return true;
  } catch (error) {
    console.error(`✗ Failed to capture ${screenshot.name}:`, error);
    try {
      await page.screenshot({ path: path.join(OUTPUT_DIR, `${screenshot.name}-error.png`) });
    } catch (e) {}
    return false;
  }
}

async function main() {
  console.log('Screenshot Capture Script');
  console.log('=========================\n');
  
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  
  try {
    // Check if account is still locked
    console.log('Checking lockout status...');
    const lockMinutes = await checkLockout(page);
    
    if (lockMinutes > 0) {
      console.log(`⚠ Account locked for ${lockMinutes} more minutes`);
      console.log(`Waiting ${lockMinutes + 1} minutes...`);
      await page.waitForTimeout((lockMinutes + 1) * 60 * 1000);
      console.log('Lockout period should be over, proceeding...\n');
    } else {
      console.log('✓ No lockout detected\n');
    }
    
    // Capture screenshots
    let success = 0;
    let failed = 0;
    
    for (const screenshot of screenshots) {
      const result = await captureScreenshot(page, screenshot);
      if (result) success++;
      else failed++;
    }
    
    console.log(`\n=========================`);
    console.log(`✓ Completed: ${success} successful, ${failed} failed`);
    
  } catch (error) {
    console.error('Fatal error:', error);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
