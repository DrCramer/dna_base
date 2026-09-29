import { expect, test } from '@playwright/test'

test('раздел протоколов открывает создание и архив', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('dna_registry.theme', 'auto'))
  await page.goto('/')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByText('ДНК реестр', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Протоколы' }).click()
  await page.getByRole('button', { name: 'Создать', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Создать протокол' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Выделение', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Real Time', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'PCR', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Форез', exact: true })).toBeVisible()
  await expect(page.getByText('Выберите объекты, чтобы построить плашку.')).toBeVisible()
  await expect(page.getByPlaceholder('№ рег РЦСМЭ от')).toBeVisible()
  await expect(page.getByPlaceholder('№ рег РЦСМЭ до')).toBeVisible()
  await expect(page.getByLabel('Описание')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Вставить список номеров' })).toBeEnabled()
  await expect(page.getByPlaceholder('Тип объекта')).toHaveCount(0)
  await expect(page.getByPlaceholder('Коробка')).toHaveCount(0)

  await page.getByRole('button', { name: 'Вставить список номеров' }).click()
  await page.getByPlaceholder('7600-1\n7601-1\n7602-1').fill('999999999-999')
  await page.getByRole('button', { name: 'Применить' }).click()
  await expect(page.getByText('Найдено: 0 из 1')).toBeVisible()
  await expect(page.getByPlaceholder('№ рег РЦСМЭ от')).toHaveCount(0)
  await expect(page.getByLabel('Описание')).toBeEnabled()
  await page.getByRole('button', { name: /Очистить список/ }).click()
  await expect(page.getByPlaceholder('№ рег РЦСМЭ от')).toBeVisible()

  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type="checkbox"]').first().check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await expect(page.getByRole('button', { name: /1 партий · \d+ объектов/ })).toBeVisible()
  await expect(page.locator('.protocol-selection-actions strong')).not.toHaveText('Выбрано: 0')
  await page.route('**/api/protocols/preview', async (route) => {
    const response = await route.fetch()
    const preview = await response.json()
    preview.dilutions = [
      { object_id: 990001, display_name: 'Без концентрации', plate_index: 1, well: 'A1', source_concentration: null, target_concentration: 0.1, total_factor: null, available: false, steps: [] },
      { object_id: 990002, display_name: 'Без разведения', plate_index: 1, well: 'B1', source_concentration: 0.05, target_concentration: 0.1, total_factor: 1, available: true, steps: [] },
      { object_id: 990003, display_name: 'Одно разведение', plate_index: 2, well: 'A10', source_concentration: 1, target_concentration: 0.1, total_factor: 10, available: true, steps: [{ factor: 10, dna_volume: 3, water_volume: 27 }] },
      { object_id: 990004, display_name: 'Два разведения', plate_index: 2, well: 'H12', source_concentration: 1000, target_concentration: 0.1, total_factor: 10000, available: true, steps: [{ factor: 100, dna_volume: 3, water_volume: 297 }, { factor: 100, dna_volume: 10, water_volume: 990 }] }
    ]
    await route.fulfill({ response, json: preview })
  })
  const pcrRecalculated = page.waitForResponse((response) => response.url().includes('/protocols/preview') && response.request().method() === 'POST')
  await page.locator('.protocol-stage').nth(2).getByLabel('Набор').selectOption({ index: 1 })
  await pcrRecalculated
  const forezRecalculated = page.waitForResponse((response) => response.url().includes('/protocols/preview') && response.request().method() === 'POST')
  await page.locator('.protocol-stage').nth(3).getByLabel('Набор').selectOption({ index: 1 })
  await forezRecalculated

  const dilutionDetails = page.locator('.protocol-dilution-summary').locator('..')
  const hideNoDilution = page.getByLabel('Скрыть объекты без разведения')
  await expect(dilutionDetails).not.toHaveAttribute('open', '')
  await hideNoDilution.check()
  await expect(dilutionDetails).not.toHaveAttribute('open', '')
  await page.getByText('Разведения', { exact: true }).click()
  await expect(dilutionDetails).toHaveAttribute('open', '')
  await expect(page.locator('.protocol-dilution-summary .protocol-details-chevron')).toHaveCSS('transform', 'matrix(0, 1, -1, 0, 0, 0)')

  const dilutionRows = page.locator('.protocol-sheet .protocol-dilution-wrap tbody tr')
  const filteredRowCount = await dilutionRows.count()
  expect(filteredRowCount).toBe(2)
  await hideNoDilution.uncheck()
  const allRowsCount = await dilutionRows.count()
  expect(allRowsCount).toBeGreaterThanOrEqual(filteredRowCount)
  await hideNoDilution.check()
  await expect(dilutionRows).toHaveCount(filteredRowCount)
  const rowsWithoutDilution = await dilutionRows.evaluateAll((rows) => rows.some((row) => {
    const cells = Array.from(row.querySelectorAll('td'))
    return cells[6]?.textContent?.trim() === '—' && cells[8]?.textContent?.trim() === '—'
  }))
  expect(rowsWithoutDilution).toBe(false)

  const plateColumnWidth = await page.locator('.protocol-sheet .protocol-dilution-wrap th.protocol-dilution-col-plate').evaluate((element) => element.getBoundingClientRect().width)
  const wellColumnWidth = await page.locator('.protocol-sheet .protocol-dilution-wrap th.protocol-dilution-col-well').evaluate((element) => element.getBoundingClientRect().width)
  expect(plateColumnWidth).toBeLessThan(90)
  expect(wellColumnWidth).toBeLessThan(90)
  const secondRow = dilutionRows.nth(1)
  const zebraBackground = await secondRow.locator('td').first().evaluate((element) => getComputedStyle(element).backgroundColor)
  await secondRow.hover()
  const hoverBackground = await secondRow.locator('td').first().evaluate((element) => getComputedStyle(element).backgroundColor)
  expect(hoverBackground).not.toBe(zebraBackground)

  const themeButton = page.getByRole('button', { name: /Тема:/ })
  await themeButton.click()
  await expect.poll(() => page.locator('html').getAttribute('data-theme')).toBe('light')
  const lightZebraBackground = await dilutionRows.nth(1).locator('td').first().evaluate((element) => getComputedStyle(element).backgroundColor)
  expect(lightZebraBackground).not.toBe('rgba(0, 0, 0, 0)')
  await themeButton.click()
  await expect.poll(() => page.locator('html').getAttribute('data-theme')).toBe('dark')
  const darkZebraBackground = await dilutionRows.nth(1).locator('td').first().evaluate((element) => getComputedStyle(element).backgroundColor)
  expect(darkZebraBackground).not.toBe(lightZebraBackground)
  await themeButton.click()
  await expect(page.getByRole('button', { name: 'Тема: авто' })).toBeVisible()

  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
  await page.getByRole('button', { name: 'Предпросмотр печати' }).click()
  await page.getByRole('button', { name: 'Предпросмотр', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Разведения', exact: true }).first()).toBeVisible()
  await expect(page.locator('.protocol-print-page').getByText('Протокол PCR', { exact: true })).toBeVisible()
  await expect(page.locator('.protocol-print-data-page .protocol-dilution-wrap th.protocol-dilution-col-plate')).toHaveCSS('white-space', 'nowrap')
  await expect(page.locator('.protocol-print-data-page .protocol-dilution-wrap table')).toHaveCSS('table-layout', 'auto')
  await page.getByRole('button', { name: 'Закрыть' }).click()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Сохранённые' }).click()
  await expect(page.getByRole('heading', { name: 'Сохранённые протоколы' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Сегодня' })).toBeVisible()
  await expect(page.getByText('Дополнительные фильтры')).toBeVisible()
})
