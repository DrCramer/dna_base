import { expect, test } from '@playwright/test'

test('поиск по файлу: год, предпросмотр, скачивание и сброс результата', async ({ page }) => {
  const rows = [{ party_no: '007', rcsme_reg_no: '001-1', external_military_no: '0005' }]
  await page.route('**/api/parties/years', (route) => route.fulfill({ json: { years: [2026, 2025], default_year: 2026 } }))
  await page.route('**/api/exports/rcsme/preview', async (route) => {
    const body = route.request().postData() || ''
    expect(body).toContain('name="case_year"')
    expect(body).toContain('2026')
    expect(body).toContain('filename="numbers.csv"')
    await route.fulfill({ json: { rows, missing: ['002-1'], ambiguous: [], duplicates: 1 } })
  })
  await page.route('**/api/exports/rcsme.xlsx', async (route) => {
    expect(route.request().postDataJSON()).toEqual(rows)
    await route.fulfill({
      contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      body: 'download test'
    })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Войти' }).click()
  await page.getByRole('button', { name: 'Поиск', exact: true }).click()
  const general = page.getByRole('tab', { name: 'Общий поиск' })
  await expect(general).toHaveAttribute('aria-selected', 'true')
  await general.press('ArrowRight')
  await page.getByLabel('Файл с номерами РЦСМЭ').setInputFiles({
    name: 'numbers.csv', mimeType: 'text/csv', buffer: Buffer.from('001-1\n001-1\n002-1')
  })
  await expect(page.getByLabel('Год регистрации')).toHaveValue('2026')
  await page.getByRole('button', { name: 'Найти номера' }).click()
  await expect(page.getByRole('table').getByRole('columnheader')).toHaveText(['№ партии', '№ рег РЦСМЭ', '№ в в/ч №522'])
  await expect(page.getByRole('cell')).toHaveText(['007', '001-1', '0005'])
  await page.getByText('Ненайденные номера (1)').click()
  await expect(page.getByText('002-1', { exact: true })).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Скачать Excel' }).click()
  expect((await download).suggestedFilename()).toBe('Сопоставление номеров РЦСМЭ.xlsx')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(391)
  await page.getByLabel('Год регистрации').selectOption('2025')
  await expect(page.getByRole('button', { name: 'Скачать Excel' })).toHaveCount(0)
})
