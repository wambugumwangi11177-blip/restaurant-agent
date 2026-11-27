import { chromium } from 'playwright';

const BASE_URL = 'https://frontend-test-production-752b1b7c.up.railway.app';
const OUTPUT_DIR = '/opt/cursor/artifacts';

async function captureLocked() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });

  try {
    // Capture login page
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.screenshot({ path: `${OUTPUT_DIR}/login-page-locked.png` });
    console.log('✓ Captured login page');
    
    // Try to login to show the error
    await page.locator('input[type="email"]').fill('owner@eleven.leviii');
    await page.locator('input[type="password"]').fill('NewPass2');
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${OUTPUT_DIR}/login-error-locked.png` });
    console.log('✓ Captured login error state');
    
    // Check lockout message
    const bodyText = await page.locator('body').textContent();
    const lockMatch = bodyText?.match(/Try again in (\d+) minute/);
    if (lockMatch) {
      console.log(`Account locked for ${lockMatch[1]} more minutes`);
    }
    
  } finally {
    await browser.close();
  }
}

captureLocked();
