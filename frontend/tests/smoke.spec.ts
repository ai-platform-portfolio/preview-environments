import { expect, test } from '@playwright/test';

test('frontend calls the Python API', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Preview environment' })).toBeVisible();

  await page.getByRole('button', { name: 'Check API' }).click();
  await expect(page.getByRole('status')).toHaveText('Hello from the Python API');
});
