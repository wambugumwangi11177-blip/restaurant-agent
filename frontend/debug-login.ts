import { chromium } from 'playwright';

const BASE_URL = 'https://frontend-test-production-752b1b7c.up.railway.app';
const OWNER_EMAIL = 'owner@eleven.leviii';
const DEFAULT_PASSWORD = 'NewPass2';

async function debugLogin() {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  try {
    console.log('Navigating to login page...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    
    console.log('Taking screenshot of initial page...');
    await page.screenshot({ path: '/opt/cursor/artifacts/debug-01-initial.png' });
    
    console.log('Page HTML:', await page.content());
    
    // Check for email login button
    const emailInsteadButton = page.locator('text=Sign in with email instead');
    const isVisible = await emailInsteadButton.isVisible({ timeout: 2000 }).catch(() => false);
    console.log('Email instead button visible:', isVisible);
    
    if (isVisible) {
      console.log('Clicking email instead button...');
      await emailInsteadButton.click();
      await page.waitForTimeout(1000);
      await page.screenshot({ path: '/opt/cursor/artifacts/debug-02-after-click.png' });
    }
    
    // Find email input
    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    console.log('Email input exists:', await emailInput.count() > 0);
    
    if (await emailInput.count() > 0) {
      console.log('Filling email...');
      await emailInput.fill(OWNER_EMAIL);
      await page.screenshot({ path: '/opt/cursor/artifacts/debug-03-email-filled.png' });
    }
    
    // Find password input
    const passwordInput = page.locator('input[type="password"], input[name="password"]').first();
    console.log('Password input exists:', await passwordInput.count() > 0);
    
    if (await passwordInput.count() > 0) {
      console.log('Filling password...');
      await passwordInput.fill(DEFAULT_PASSWORD);
      await page.screenshot({ path: '/opt/cursor/artifacts/debug-04-password-filled.png' });
    }
    
    // Find sign in button
    const signInButton = page.locator('button:has-text("Sign In"), button:has-text("Sign in")');
    console.log('Sign in buttons found:', await signInButton.count());
    
    if (await signInButton.count() > 0) {
      console.log('Clicking sign in button...');
      await signInButton.first().click();
      await page.screenshot({ path: '/opt/cursor/artifacts/debug-05-after-signin.png' });
      
      // Wait and see what happens
      await page.waitForTimeout(5000);
      await page.screenshot({ path: '/opt/cursor/artifacts/debug-06-after-wait.png' });
      
      console.log('Current URL:', page.url());
      console.log('Page title:', await page.title());
    }
    
  } catch (error) {
    console.error('Error:', error);
    await page.screenshot({ path: '/opt/cursor/artifacts/debug-error.png' });
  } finally {
    await browser.close();
  }
}

debugLogin();
