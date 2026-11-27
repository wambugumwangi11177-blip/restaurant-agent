import { chromium } from 'playwright';
import type { Browser, Page } from 'playwright';
import * as path from 'path';

const BASE_URL = 'https://frontend-test-production-752b1b7c.up.railway.app';
const OUTPUT_DIR = '/opt/cursor/artifacts';

// Test credentials from leviii_test_seed.py
const OWNER_EMAIL = 'owner@eleven.leviii';
const JACK_EMAIL = 'jack@eleven.leviii';
const AMINA_EMAIL = 'amina@eleven.leviii';

// Try different passwords
const PASSWORDS_TO_TRY = ['NewPass2', 'password', 'Password123!', 'admin'];

interface Screenshot {
  name: string;
  url: string;
  email: string;
  password?: string;
  waitForSelector?: string;
  actions?: (page: Page) => Promise<void>;
}

const screenshots: Screenshot[] = [
  // Owner flows
  { name: 'owner-home', url: '/eleven', email: OWNER_EMAIL, waitForSelector: 'text=LEVIII STORE' },
  { name: 'owner-dishes', url: '/eleven/dishes', email: OWNER_EMAIL, waitForSelector: 'text=Dishes' },
  { name: 'owner-money', url: '/eleven/money', email: OWNER_EMAIL, waitForSelector: 'text=Money' },
  { name: 'owner-alerts', url: '/eleven/alerts', email: OWNER_EMAIL, waitForSelector: 'text=Alerts' },
  { name: 'owner-handover-timeline', url: '/eleven/handover', email: OWNER_EMAIL, waitForSelector: 'text=Handover' },
  
  // Jack flows
  { name: 'jack-wizard-step1', url: '/store', email: JACK_EMAIL, waitForSelector: 'text=Home' },
  { name: 'jack-restock-whatsapp', url: '/store/requests', email: JACK_EMAIL, waitForSelector: 'text=Requests' },
  { name: 'store-prep-list', url: '/store/recipes', email: JACK_EMAIL, waitForSelector: 'text=Recipes' },
  
  // Accountant/controller flows
  { name: 'accountant-invoice-prices', url: '/store', email: AMINA_EMAIL, waitForSelector: 'text=Home' },
];

async function tryLogin(page: Page, email: string): Promise<{ success: boolean; password?: string; error?: string }> {
  for (const password of PASSWORDS_TO_TRY) {
    try {
      console.log(`  Trying password: ${password.substring(0, 3)}...`);
      
      // Go to login page
      await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 15000 });
      
      // Fill in credentials
      const emailInput = page.locator('input[type="email"], input[name="email"], input[name="username"]').first();
      await emailInput.fill(email);
      
      const passwordInput = page.locator('input[type="password"], input[name="password"]').first();
      await passwordInput.fill(password);
      
      // Click sign in button
      const signInButton = page.locator('button:has-text("Sign in"), button[type="submit"]').first();
      await signInButton.click();
      
      // Wait a bit for response
      await page.waitForTimeout(3000);
      
      // Check if we're still on login page (failed) or redirected (success)
      const currentUrl = page.url();
      if (!currentUrl.includes('/login')) {
        console.log(`  ✓ Login successful with password`);
        return { success: true, password };
      }
      
      // Check for error message
      const errorText = await page.locator('text=/error|invalid|incorrect|wrong/i').first().textContent().catch(() => null);
      if (errorText) {
        console.log(`  ✗ Error: ${errorText}`);
      }
      
    } catch (error) {
      console.log(`  ✗ Error trying password: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  
  return { success: false, error: 'All passwords failed' };
}

async function captureScreenshot(browser: Browser, screenshot: Screenshot, workingPasswords: Map<string, string>): Promise<void> {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  
  const page = await context.newPage();
  
  try {
    console.log(`\nCapturing: ${screenshot.name}`);
    
    // Try login if we don't have a working password yet
    let password = workingPasswords.get(screenshot.email);
    if (!password) {
      console.log(`Attempting login for ${screenshot.email}...`);
      const loginResult = await tryLogin(page, screenshot.email);
      if (!loginResult.success) {
        console.log(`⚠ Skipping ${screenshot.name} - login failed`);
        await page.screenshot({
          path: path.join(OUTPUT_DIR, `${screenshot.name}-login-failed.png`),
        });
        return;
      }
      password = loginResult.password!;
      workingPasswords.set(screenshot.email, password);
    } else {
      // Use known working password
      await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
      await page.locator('input[type="email"], input[name="email"], input[name="username"]').first().fill(screenshot.email);
      await page.locator('input[type="password"], input[name="password"]').first().fill(password);
      await page.locator('button:has-text("Sign in"), button[type="submit"]').first().click();
      await page.waitForTimeout(2000);
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
    await page.waitForTimeout(2000);
    
    // Execute custom actions if provided
    if (screenshot.actions) {
      await screenshot.actions(page);
    }
    
    // Capture screenshot
    const outputPath = path.join(OUTPUT_DIR, `${screenshot.name}.png`);
    await page.screenshot({ path: outputPath });
    
    console.log(`✓ Saved: ${outputPath}`);
  } catch (error) {
    console.error(`✗ Failed to capture ${screenshot.name}:`, error);
    
    try {
      await page.screenshot({
        path: path.join(OUTPUT_DIR, `${screenshot.name}-error.png`),
      });
    } catch (e) {
      // Ignore
    }
  } finally {
    await context.close();
  }
}

async function main() {
  console.log('Starting screenshot capture...');
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Output directory: ${OUTPUT_DIR}`);
  
  const browser = await chromium.launch({ headless: true });
  const workingPasswords = new Map<string, string>();
  
  try {
    for (const screenshot of screenshots) {
      await captureScreenshot(browser, screenshot, workingPasswords);
    }
    
    console.log('\n✓ Screenshot capture complete!');
    console.log('\nWorking credentials:');
    for (const [email, password] of workingPasswords) {
      console.log(`  ${email}: ${password}`);
    }
  } catch (error) {
    console.error('Fatal error:', error);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
