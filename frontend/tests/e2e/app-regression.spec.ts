import { expect, type Page, test } from '@playwright/test';

const demoEmail = process.env.PLAYWRIGHT_DEMO_EMAIL || 'demo@cacopilot.example.com';
const demoPassword = process.env.PLAYWRIGHT_DEMO_PASSWORD || 'DemoPass123';
const apiURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000';

const moduleRoutes = [
  '/',
  '/clients',
  '/documents',
  '/reconciliation',
  '/deadlines',
  '/whatsapp',
  '/notices',
  '/audit',
  '/anomalies',
  '/invoices',
  '/query',
  '/benchmarking',
  '/autopilot',
  '/work',
  '/billing',
  '/portal',
  '/team',
  '/vault',
  '/imports',
  '/reports',
  '/diagnostics',
  '/msme',
  '/drawing-power',
  '/certificates',
  '/secretarial',
  '/leases',
  '/rfp',
  '/timesheets',
];

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(demoEmail);
  await page.getByLabel('Password').fill(demoPassword);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL(/\/$/, { timeout: 30_000 });
}

async function authenticate(page: Page) {
  const response = await page.request.post(`${apiURL}/auth/login`, {
    data: { email: demoEmail, password: demoPassword },
  });
  expect(response.ok()).toBeTruthy();
  const tokens = await response.json();
  await page.addInitScript(([accessToken, refreshToken]) => {
    window.localStorage.setItem('access_token', accessToken);
    window.localStorage.setItem('refresh_token', refreshToken);
  }, [tokens.access_token, tokens.refresh_token]);
}

test('demo user can sign in and view readiness diagnostics', async ({ page }) => {
  await login(page);
  await page.goto('/diagnostics');
  await expect(page.getByRole('heading', { name: 'Diagnostics' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Integrations' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Security Controls' })).toBeVisible();
});

test('password reset request screen is reachable', async ({ page }) => {
  await page.goto('/forgot-password');
  await page.getByLabel('Email').fill(demoEmail);
  await page.getByRole('button', { name: 'Send reset link' }).click();
  await expect(page.getByText(/reset link has been sent/i)).toBeVisible();
});

for (const route of moduleRoutes) {
  test(`authenticated module route renders: ${route}`, async ({ page }) => {
    await authenticate(page);
    await page.goto(route);
    await expect(page.locator('body')).not.toContainText('Application error');
    await expect(page.locator('body')).not.toContainText('Network Error');
  });
}

test('billing page exposes invoice and payment workflows', async ({ page }) => {
  await authenticate(page);
  await page.goto('/billing');
  await expect(page.getByRole('heading', { name: 'Billing & Collections' })).toBeVisible();
  await expect(page.getByText('Invoice register')).toBeVisible();
  await expect(page.getByText('Record payment')).toBeVisible();
});
