import { chromium } from 'playwright';
import type { Page } from 'playwright';
import * as path from 'path';

const BASE_URL = 'https://frontend-test-production-752b1b7c.up.railway.app';
const OUTPUT_DIR = '/opt/cursor/artifacts';

const OWNER_EMAIL = 'owner@eleven.leviii';
const OWNER_PASSWORD = 'VOpyWqNTRSnvaSS1'; // Actual password from credentials file
const JACK_EMAIL = 'jack@eleven.leviii';
const AMINA_EMAIL = 'amina@eleven.leviii';

interface Screenshot {
  name: string;
  url: string;
  email: string;
  password: string;
  waitFor?: string;
}

const screenshots: Screenshot[] = [
  { name: 'owner-home', url: '/eleven', email: OWNER_EMAIL, password: OWNER_PASSWORD },
  { name: 'owner-dishes', url: '/eleven/dishes', email: OWNER_EMAIL, password: OWNER_PASSWORD },
  { name: 'owner-money', url: '/eleven/money', email: OWNER_EMAIL, password: OWNER_PASSWORD },
  { name: 'owner-alerts', url: '/eleven/alerts', email: OWNER_EMAIL, password: OWNER_PASSWORD },
  { name: 'owner-handover-timeline', url: '/eleven/handover', email: OWNER_EMAIL, password: OWNER_PASSWORD },
];

// Note: Jack and Amina require first-time password setup, so we'll skip them for now
// and report that blocker

async function login(page: Page, email: string, password: string): Promise<boolean> {
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="password"]').fill(password);
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(3000);
    
    const url = page.url();
    if (!url.includes('/login')) {
      console.log(`✓ Login successful for ${email}`);
      return true;
    }
    
    const bodyText = await page.locator('body').textContent() || '';
    if (bodyText.includes('locked')) {
      console.log(`⚠ Account locked for ${email}`);
    } else {
      console.log(`✗ Login failed for ${email}`);
    }
    return false;
  } catch (error) {
    console.log(`✗ Login error for ${email}:`, error instanceof Error ? error.message : String(error));
    return false;
  }
}

async function captureScreenshot(page: Page, screenshot: Screenshot): Promise<boolean> {
  try {
    console.log(`\nCapturing: ${screenshot.name}`);
    
    // Login
    const success = await login(page, screenshot.email, screenshot.password);
    if (!success) {
      await page.screenshot({ path: path.join(OUTPUT_DIR, `${screenshot.name}-login-failed.png`) });
      return false;
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
    console.error(`✗ Failed to capture ${screenshot.name}:`, error instanceof Error ? error.message : String(error));
    try {
      await page.screenshot({ path: path.join(OUTPUT_DIR, `${screenshot.name}-error.png`) });
    } catch (e) {}
    return false;
  }
}

async function main() {
  console.log('Screenshot Capture Script - Final Attempt');
  console.log('==========================================\n');
  
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  
  try {
    let success = 0;
    let failed = 0;
    
    for (const screenshot of screenshots) {
      const result = await captureScreenshot(page, screenshot);
      if (result) success++;
      else failed++;
    }
    
    console.log(`\n==========================================`);
    console.log(`✓ Owner screenshots: ${success} successful, ${failed} failed`);
    console.log(`\n⚠ Skipped Jack/Amina screenshots:`);
    console.log(`  - jack-wizard-step1`);
    console.log(`  - jack-restock-whatsapp`);
    console.log(`  - store-prep-list`);
    console.log(`  - accountant-invoice-prices`);
    console.log(`\nReason: These accounts require first-time password setup.`);
    console.log(`Password field shows: "set on first sign-in"`);
    
  } catch (error) {
    console.error('Fatal error:', error);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
