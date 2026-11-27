import { chromium } from 'playwright';

const BASE_URL = 'https://frontend-test-production-752b1b7c.up.railway.app';
const OWNER_EMAIL = 'owner@eleven.leviii';
const OWNER_PASSWORD = 'VOpyWqNTRSnvaSS1';

async function checkLockout() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.locator('input[type="email"]').fill(OWNER_EMAIL);
    await page.locator('input[type="password"]').fill(OWNER_PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(2000);
    
    const bodyText = await page.locator('body').textContent();
    const lockMatch = bodyText?.match(/Try again in (\d+) minute/);
    if (lockMatch) {
      const minutes = parseInt(lockMatch[1]);
      console.log(`Account still locked for ${minutes} more minutes`);
      console.log(`Current time: ${new Date().toISOString()}`);
      const unlockTime = new Date(Date.now() + minutes * 60 * 1000);
      console.log(`Unlock time: ${unlockTime.toISOString()}`);
    } else {
      console.log('No lockout detected - ready to proceed!');
    }
    
    await page.screenshot({ path: '/opt/cursor/artifacts/lockout-status-final.png' });
  } finally {
    await browser.close();
  }
}

checkLockout();
