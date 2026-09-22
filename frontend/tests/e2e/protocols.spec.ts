import { expect, test } from '@playwright/test'

test('раздел протоколов открывает создание и архив', async ({ page }) => {
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

  await page.getByRole('button', { name: 'Сохранённые' }).click()
  await expect(page.getByRole('heading', { name: 'Сохранённые протоколы' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Сегодня' })).toBeVisible()
  await expect(page.getByText('Дополнительные фильтры')).toBeVisible()
})
