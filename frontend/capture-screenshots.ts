import { chromium } from 'playwright';
import type { Browser, Page } from 'playwright';
import * as path from 'path';

const BASE_URL = 'https://frontend-test-production-752b1b7c.up.railway.app';
const OUTPUT_DIR = '/opt/cursor/artifacts';

// Test credentials from leviii_test_seed.py
const OWNER_EMAIL = 'owner@eleven.leviii';
const JACK_EMAIL = 'jack@eleven.leviii';
const AMINA_EMAIL = 'amina@eleven.leviii';

// Passwords - these users require password on first login
const DEFAULT_PASSWORD = 'NewPass2'; // Common test password

interface Screenshot {
  name: string;
  url: string;
  email: string;
  password: string;
  waitForSelector?: string;
  actions?: (page: Page) => Promise<void>;
}

const screenshots: Screenshot[] = [
  // Owner flows
  {
    name: 'owner-home',
    url: '/eleven',
    email: OWNER_EMAIL,
    password: DEFAULT_PASSWORD,
    waitForSelector: 'text=LEVIII STORE',
  },
  {
    name: 'owner-dishes',
    url: '/eleven/dishes',
    email: OWNER_EMAIL,
    password: DEFAULT_PASSWORD,
    waitForSelector: 'text=Dishes',
  },
  {
    name: 'owner-money',
    url: '/eleven/money',
    email: OWNER_EMAIL,
    password: DEFAULT_PASSWORD,
    waitForSelector: 'text=Money',
  },
  {
    name: 'owner-alerts',
    url: '/eleven/alerts',
    email: OWNER_EMAIL,
    password: DEFAULT_PASSWORD,
    waitForSelector: 'text=Alerts',
  },
  {
    name: 'owner-handover-timeline',
    url: '/eleven/handover',
    email: OWNER_EMAIL,
    password: DEFAULT_PASSWORD,
    waitForSelector: 'text=Handover',
  },
  
  // Jack flows
  {
    name: 'jack-wizard-step1',
    url: '/store',
    email: JACK_EMAIL,
    password: DEFAULT_PASSWORD,
    waitForSelector: 'text=Home',
  },
  {
    name: 'jack-restock-whatsapp',
    url: '/store/requests',
    email: JACK_EMAIL,
    password: DEFAULT_PASSWORD,
    waitForSelector: 'text=Requests',
  },
  {
    name: 'store-prep-list',
    url: '/store/recipes',
    email: JACK_EMAIL,
    password: DEFAULT_PASSWORD,
    waitForSelector: 'text=Recipes',
  },
  
  // Accountant/controller flows
  {
    name: 'accountant-invoice-prices',
    url: '/store',
    email: AMINA_EMAIL,
    password: DEFAULT_PASSWORD,
    waitForSelector: 'text=Home',
  },
];

async function login(page: Page, email: string, password: string): Promise<boolean> {
  try {
    console.log(`Attempting login for ${email}...`);
    
    // Go to login page
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    
    // Check if we need to switch to email login
    const emailInsteadButton = page.locator('text=Sign in with email instead');
    if (await emailInsteadButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await emailInsteadButton.click();
      await page.waitForTimeout(500);
    }
    
    // Fill in credentials
    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    await emailInput.fill(email);
    
    const passwordInput = page.locator('input[type="password"], input[name="password"]').first();
    await passwordInput.fill(password);
    
    // Click sign in button
    const signInButton = page.locator('button:has-text("Sign In"), button:has-text("Sign in")').first();
    await signInButton.click();
    
    // Wait for navigation
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10000 });
    
    console.log(`✓ Login successful for ${email}`);
    return true;
  } catch (error) {
    console.error(`✗ Login failed for ${email}:`, error);
    return false;
  }
}

async function captureScreenshot(browser: Browser, screenshot: Screenshot): Promise<void> {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 }, // Mobile viewport
    deviceScaleFactor: 2,
  });
  
  const page = await context.newPage();
  
  try {
    console.log(`\nCapturing: ${screenshot.name}`);
    
    // Login
    const loginSuccess = await login(page, screenshot.email, screenshot.password);
    if (!loginSuccess) {
      console.log(`⚠ Skipping ${screenshot.name} due to login failure`);
      await page.screenshot({
        path: path.join(OUTPUT_DIR, `${screenshot.name}-login-failed.png`),
        fullPage: false,
      });
      return;
    }
    
    // Navigate to target URL
    await page.goto(`${BASE_URL}${screenshot.url}`, { waitUntil: 'networkidle', timeout: 15000 });
    
    // Wait for specific selector if provided
    if (screenshot.waitForSelector) {
      await page.waitForSelector(screenshot.waitForSelector, { timeout: 10000 }).catch(() => {
        console.log(`⚠ Selector not found: ${screenshot.waitForSelector}`);
      });
    }
    
    // Additional wait for content to stabilize
    await page.waitForTimeout(1500);
    
    // Execute custom actions if provided
    if (screenshot.actions) {
      await screenshot.actions(page);
    }
    
    // Capture screenshot
    const outputPath = path.join(OUTPUT_DIR, `${screenshot.name}.png`);
    await page.screenshot({
      path: outputPath,
      fullPage: false, // Capture viewport only for consistency
    });
    
    console.log(`✓ Saved: ${outputPath}`);
  } catch (error) {
    console.error(`✗ Failed to capture ${screenshot.name}:`, error);
    
    // Try to save error screenshot
    try {
      await page.screenshot({
        path: path.join(OUTPUT_DIR, `${screenshot.name}-error.png`),
        fullPage: false,
      });
    } catch (e) {
      console.error(`Could not save error screenshot: ${e}`);
    }
  } finally {
    await context.close();
  }
}

async function main() {
  console.log('Starting screenshot capture...');
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Output directory: ${OUTPUT_DIR}`);
  
  const browser = await chromium.launch({
    headless: true,
  });
  
  try {
    for (const screenshot of screenshots) {
      await captureScreenshot(browser, screenshot);
    }
    
    console.log('\n✓ Screenshot capture complete!');
  } catch (error) {
    console.error('Fatal error:', error);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
