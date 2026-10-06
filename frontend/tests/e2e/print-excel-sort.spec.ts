import { expect, test, type Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'

type ExcelValidation = {
  mode: string
  groups: Array<{ id: string; column: string; excel_file: string; validation: { entries: Array<{ number: string; doc_id: string | null; assigned_number?: string }> } }>
}

const firstExcel = fileURLToPath(new URL('../fixtures/print-order-columns.xlsx', import.meta.url))
const secondExcel = fileURLToPath(new URL('../fixtures/print-order-second.xlsx', import.meta.url))
const numbers = ['ии1', 'ии2', 'ии10', 'нн1', 'нн2', 'нн10', 'ее2', 'ее100']
const sortedColumns = [['ии1', 'ии2', 'ии10'], ['нн1', 'нн2', 'нн10'], ['ее2', 'ее100']]

async function openExcelTask(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await expect(page.getByText('ДНК реестр', { exact: true })).toBeVisible()
  const multipart = new FormData()
  numbers.forEach((number) => multipart.append('files', new Blob([number], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }), `Акт_${number}.docx`))
  const uploaded = await page.request.post('/api/print/jobs', { multipart })
  expect(uploaded.ok()).toBe(true)
  const job = await uploaded.json() as { id: string }
  await page.evaluate((id) => {
    localStorage.setItem('docxPrintOrder.jobId', id)
    localStorage.setItem('docxPrintOrder.mode', 'excel')
    localStorage.removeItem('docxPrintOrder.stampUi')
  }, job.id)
  await page.goto('/print?embedded=1')
  await expect(page.locator('#excelModePanel')).toBeVisible()
  await page.locator('#xlsxInput').setInputFiles(firstExcel)
  await page.locator('#xlsxInput').setInputFiles(secondExcel)
  return job.id
}

async function storedColumns(page: Page, jobId: string) {
  const response = await page.request.get(`/api/print/jobs/${jobId}`)
  const job = await response.json() as { validation: ExcelValidation }
  return job.validation.groups.map((group) => group.validation.entries.map((entry) => entry.number))
}

test('сортировка столбцов сохраняется при повторной проверке и открытии задачи', async ({ page }) => {
  const jobId = await openExcelTask(page)
  try {
    await page.locator('#validateExcelButton').click()
    await expect(page.locator('#sortExcelButton')).toBeEnabled()
    expect(await storedColumns(page, jobId)).toEqual([['ии10', 'ии2', 'ии1'], ['нн10', 'нн2', 'нн1'], ['ее100', 'ее2']])
    await page.locator('#sortExcelButton').click()
    await expect.poll(() => storedColumns(page, jobId)).toEqual(sortedColumns)
    await expect(page.locator('#validateExcelButton')).toBeEnabled()
    await page.locator('#stampStartNumberInput').fill('0001-2026')
    const checked = page.waitForResponse((response) => response.request().method() === 'POST' && /\/(?:validate|sort)\/excel$/.test(new URL(response.url()).pathname))
    await page.locator('#validateExcelButton').click()
    expect((await checked).ok()).toBe(true)
    expect(await storedColumns(page, jobId)).toEqual(sortedColumns)
    const response = await page.request.get(`/api/print/jobs/${jobId}`)
    const saved = await response.json() as { validation: ExcelValidation }
    expect(saved.validation.groups.map((group) => group.column)).toEqual(['A', 'C', 'A'])
    expect(new Set(saved.validation.groups.map((group) => group.id)).size).toBe(3)
    expect(saved.validation.groups.flatMap((group) => group.validation.entries.map((entry) => entry.assigned_number))).toEqual(numbers.map((_, index) => `${String(index + 1).padStart(4, '0')}-2026`))
    await page.reload()
    await page.locator('[data-step="order"]').click()
    await expect(page.locator('#validateExcelButton')).toBeEnabled()
    const rechecked = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/sort/excel'))
    await page.locator('#validateExcelButton').click()
    expect((await rechecked).ok()).toBe(true)
    expect(await storedColumns(page, jobId)).toEqual(sortedColumns)
  } finally {
    await page.request.delete(`/api/print/jobs/${jobId}`)
  }
})

test('Excel можно отсортировать сразу после добавления файлов', async ({ page }) => {
  const jobId = await openExcelTask(page)
  try {
    await expect(page.locator('#sortExcelButton')).toBeEnabled()
    await page.locator('#sortExcelButton').click()
    await expect.poll(() => storedColumns(page, jobId)).toEqual(sortedColumns)
    await expect(page.locator('#excelFileState')).toContainText('Обнаружено рабочих столбцов: 3')
    await expect(page.locator('#clearExcelFilesButton')).toBeEnabled()
    await page.locator('#clearExcelFilesButton').click()
    await expect(page.locator('#sortExcelButton')).toBeDisabled()
    await page.locator('#xlsxInput').setInputFiles(secondExcel)
    const checked = page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/validate/excel'))
    await page.locator('#validateExcelButton').click()
    expect((await checked).ok()).toBe(true)
    expect(await storedColumns(page, jobId)).toEqual([['ее100', 'ее2']])
  } finally {
    await page.request.delete(`/api/print/jobs/${jobId}`)
  }
})
