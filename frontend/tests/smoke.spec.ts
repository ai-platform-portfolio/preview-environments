import { randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';

test('message survives a page reload through the frontend, API and database', async ({ page }) => {
  const text = `Browser persistence check ${randomUUID()}`;
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Preview environment' })).toBeVisible();
  await page.getByLabel('Message', { exact: true }).fill(text);
  await page.getByRole('button', { name: 'Save message' }).click();
  await expect(page.getByRole('status')).toHaveText(text);
  const id = await page.getByLabel('Message ID', { exact: true }).inputValue();
  expect(id).toMatch(/^[0-9a-f-]{36}$/);

  await page.reload();
  await expect(page.getByRole('status')).toHaveText('Ready');
  await page.getByLabel('Message ID', { exact: true }).fill(id);
  await page.getByRole('button', { name: 'Read message' }).click();
  await expect(page.getByRole('status')).toHaveText(text);
});
