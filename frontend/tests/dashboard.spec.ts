import { expect, test } from '@playwright/test'

test('renders the migration workspace and API panels', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle('Migration Lab — Workspace')
  await expect(page.getByRole('heading', { name: /Change the schema/ })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'One step at a time.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Legacy API' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Modern API' })).toBeVisible()
  await expect(page.getByText(/CURRENT STAGE/)).toBeVisible()
})

test('moves the local demo through initialization and legacy creation', async ({ page }) => {
  await page.goto('/')
  const initialize = page.getByRole('button', { name: 'Initialize database' })
  if (await initialize.isVisible()) {
    await initialize.click()
    await expect(page.getByRole('status').getByText('Database initialized. The legacy API is ready.')).toBeVisible()
  }
  await page.getByLabel('Full name').fill('Frontend User')
  await page.getByRole('button', { name: 'Create user' }).first().click()
  await expect(page.getByRole('status').getByText('User created through API v1.')).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Frontend User' })).toBeVisible()
})
