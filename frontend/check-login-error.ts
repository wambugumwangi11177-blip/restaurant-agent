import { chromium } from 'playwright';

const BASE_URL = 'https://frontend-test-production-752b1b7c.up.railway.app';

async function checkLoginError() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    
    // Fill credentials
    await page.locator('input[type="email"]').fill('owner@eleven.leviii');
    await page.locator('input[type="password"]').fill('NewPass2');
    
    // Take before screenshot
    await page.screenshot({ path: '/opt/cursor/artifacts/before-submit.png' });
    
    // Submit
    await page.locator('button[type="submit"]').click();
    
    // Wait for response
    await page.waitForTimeout(5000);
    
    // Take after screenshot
    await page.screenshot({ path: '/opt/cursor/artifacts/after-submit.png' });
    
    // Get current URL
    console.log('Current URL:', page.url());
    
    // Get all text content
    const bodyText = await page.locator('body').textContent();
    console.log('Page text:', bodyText);
    
    // Look for specific error patterns
    const errors = await page.locator('[class*="error"], [role="alert"], text=/error|invalid|incorrect/i').all();
    console.log('Found error elements:', errors.length);
    for (const error of errors) {
      const text = await error.textContent();
      console.log('Error text:', text);
    }
    
  } finally {
    await browser.close();
  }
}

checkLoginError();
