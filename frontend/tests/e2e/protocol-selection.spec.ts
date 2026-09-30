import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { Protocol, ProtocolObject, ProtocolPayload, ProtocolPreview } from '../../src/api/types'
import { protocolNumbers, protocolObjectIds, selectionCaption } from '../../src/components/protocols/protocolSelection'

test('уникальные ID и TXT используют порядок snapshot, включая старые object_id', () => {
  const objects = [{ id: 2, rcsme_reg_no: 'ии2' }, { object_id: 10, rcsme_reg_no: 'ии10' }, { id: 2, rcsme_reg_no: 'ии2' }, { id: 100, rcsme_reg_no: 'ии100' }]
  expect(protocolObjectIds(objects)).toEqual([2, 10, 100])
  expect(protocolNumbers(objects)).toBe('ии2\nии10\nии100')
  const selection = { case_year: 2026, party_ids: [], rcsme_from: '3001-1', rcsme_to: null, description: null, numbers: [] }
  expect(selectionCaption(selection)).toBe('Диапазон номеров: от 3001-1')
  expect(selectionCaption({ ...selection, rcsme_from: null, rcsme_to: '3020-1' })).toBe('Диапазон номеров: до 3020-1')
})

async function fixture(page: Page) {
  const year = new Date().getFullYear()
  const objects: ProtocolObject[] = Array.from({ length: 120 }, (_, index) => ({
    id: index + 1, party_id: 205, party_no: '205', case_year: year, rcsme_reg_no: `${3001 + index}-1`,
    object_description: index < 20 ? 'кость' : 'ткань', decree_no: null, external_military_no: null,
    object_type: 'sample', box_no: null, has_rt: index % 2 === 0,
    stage_types: ['dna_extraction', 'realtime', 'pcr', 'electrophoresis']
  }))
  let saved: Protocol | null = null
  let selectionRequests = 0
  let previewRequests = 0
  let delayedRange: string | null = null
  let delayedRangeRequested = false
  await page.route('**/api/parties/years', (route) => route.fulfill({ json: { years: [year, year - 1], default_year: year } }))
  await page.route('**/api/parties?**', (route) => route.fulfill({ json: { items: [{ id: 205, party_no: '205', case_year: year, object_count: 120, status: 'active', raw_control_json: {} }], total: 1 } }))
  await page.route('**/api/protocols/objects**', async (route) => {
    const url = new URL(route.request().url())
    const p = url.searchParams
    if (url.pathname.endsWith('/filter-options')) { await route.fulfill({ json: ['кость', 'ткань'] }); return }
    const isResolve = url.pathname.endsWith('/resolve')
    const numbers = (p.get('numbers') || '').split(',').filter(Boolean)
    const isCriteria = isResolve && (p.has('rcsme_from') || p.has('rcsme_to') || p.has('description') || numbers.length)
    if (isCriteria) selectionRequests++
    let rows = objects.filter((item) => item.case_year === Number(p.get('case_year') || year))
    if (!p.get('party_ids') && !numbers.length) rows = []
    if (numbers.length) rows = rows.filter((item) => numbers.includes(item.rcsme_reg_no || ''))
    if (p.get('rcsme_from')) rows = rows.filter((item) => Number(item.rcsme_reg_no?.split('-')[0]) >= Number(p.get('rcsme_from')?.split('-')[0]))
    if (p.get('rcsme_to')) rows = rows.filter((item) => Number(item.rcsme_reg_no?.split('-')[0]) <= Number(p.get('rcsme_to')?.split('-')[0]))
    if (p.get('description')) rows = rows.filter((item) => item.object_description === p.get('description'))
    if (p.get('q')) rows = rows.filter((item) => item.rcsme_reg_no?.includes(p.get('q') || ''))
    if (p.get('quick') === 'selected') rows = rows.filter((item) => (p.get('selected_ids') || '').split(',').includes(String(item.id)))
    if (p.get('quick') === 'has_rt') rows = rows.filter((item) => item.has_rt)
    if (p.get('quick') === 'no_rt') rows = rows.filter((item) => !item.has_rt)
    if (!isResolve) {
      expect(p.has('rcsme_from') || p.has('rcsme_to') || p.has('description')).toBe(false)
      const offset = Number(p.get('offset') || 0)
      await route.fulfill({ json: { items: rows.slice(offset, offset + 100), total: rows.length, limit: 100, offset } })
    } else {
      if (delayedRange && p.get('rcsme_from') === delayedRange) {
        delayedRangeRequested = true
        await new Promise((resolve) => setTimeout(resolve, 1200))
      }
      await route.fulfill({ json: { object_ids: rows.map((item) => item.id), total: rows.length, matched_numbers: numbers.filter((number) => rows.some((item) => item.rcsme_reg_no === number)), missing_numbers: numbers.filter((number) => !rows.some((item) => item.rcsme_reg_no === number)) } })
    }
  })
  function preview(payload: ProtocolPayload): ProtocolPreview {
    const selected = objects.filter((item) => payload.object_ids.includes(item.id)).map((item) => ({ ...item }))
    const plates = Array.from({ length: Math.ceil(selected.length / 95) }, (_, index) => {
      const samples = selected.slice(index * 95, (index + 1) * 95)
      return { plate_index: index + 1, sample_count: samples.length, wells: Array.from({ length: 96 }, (_, wellIndex) => {
        const object = samples[wellIndex]
        return { plate_index: index + 1, well: `${'ABCDEFGH'[wellIndex % 8]}${Math.floor(wellIndex / 8) + 1}`, kind: object ? 'sample' as const : wellIndex === 95 ? 'nc' as const : 'empty' as const, object_id: object?.id ?? null, display_name: object?.rcsme_reg_no || (wellIndex === 95 ? 'NC' : ''), label: null, order_index: wellIndex }
      }) }
    })
    const layouts = { source: { layout_key: 'source', capacity: 95, rules: {}, plates, warnings: [] }, pcr: { layout_key: 'pcr', capacity: 95, rules: {}, plates, warnings: [] } }
    const stages = payload.stages.map((stage) => ({ ...stage, performers: [] }))
    const calculations = { pcr: [], electrophoresis: { components: [] } }
    return { selected_count: selected.length, capacity: 95, max_capacity: 96, objects: selected, stages, layouts, calculations, dilutions: [], warnings: [], snapshot: { protocol: payload, objects: selected, stages, layouts, calculations, dilutions: [], warnings: [], selection: payload.selection, plate_rules: payload.plate_rules, dilution_settings: payload.dilution } }
  }
  await page.route('**/api/protocols/preview', async (route) => {
    previewRequests++
    await route.fulfill({ json: preview(route.request().postDataJSON() as ProtocolPayload) })
  })
  await page.route(/\/api\/protocols(?:\?.*)?$/, async (route) => {
    if (route.request().method() === 'POST') {
      const payload = route.request().postDataJSON() as ProtocolPayload
      const stamp = new Date().toISOString()
      saved = { id: 999001, series_key: 'selection-test', protocol_no: payload.protocol_no, protocol_date: payload.protocol_date, name: payload.name, status: 'draft', revision_no: 1, comment: payload.comment, created_by_user_id: null, created_at: stamp, updated_at: stamp, finalized_at: null, snapshot: preview(payload).snapshot, revisions: [{ id: 999001, revision_no: 1, status: 'draft', updated_at: stamp }] }
      await route.fulfill({ json: saved })
    } else {
      await route.fulfill({ json: { items: saved ? [{ ...saved, object_count: protocolObjectIds(saved.snapshot.objects as Record<string, unknown>[]).length, party_numbers: ['205'], stage_types: ['dna_extraction', 'realtime', 'pcr', 'electrophoresis'], author: 'admin' }] : [], total: saved ? 1 : 0, limit: 50, offset: 0 } })
    }
  })
  await page.route('**/api/protocols/999001', async (route) => { await route.fulfill({ json: saved }) })
  await page.goto('/')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByText('ДНК реестр', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Протоколы' }).click()
  await page.getByRole('button', { name: 'Создать', exact: true }).click()
  return { objects, saved: () => saved, selectionRequests: () => selectionRequests, previewRequests: () => previewRequests, delay: (range: string) => { delayedRange = range }, delayedRangeRequested: () => delayedRangeRequested }
}

test('диапазон и описание отмечают объекты, ручной выбор сохраняется и выгружается', async ({ page }, testInfo) => {
  test.setTimeout(60_000)
  const state = await fixture(page)
  const rows = page.locator('.protocol-object-table tbody tr')
  const count = page.locator('.protocol-selection-actions strong')
  const row = (number: string) => rows.filter({ has: page.getByText(number, { exact: true }) })
  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type=checkbox]').check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await expect(count).toHaveText('Выбрано: 120')
  await expect(rows).toHaveCount(100)
  await expect(page.getByText('1–100 из 120', { exact: true })).toBeVisible()
  await page.getByPlaceholder('№ рег РЦСМЭ от').fill('3001-1')
  await page.getByPlaceholder('№ рег РЦСМЭ до').fill('3020-1')
  await expect(count).toHaveText('Выбрано: 20')
  await expect(rows).toHaveCount(100)
  await expect(row('3021-1').getByRole('checkbox')).not.toBeChecked()
  await page.getByPlaceholder('№ рег РЦСМЭ до').fill('3025-1')
  await expect(count).toHaveText('Выбрано: 25')
  await page.getByLabel('Описание', { exact: true }).selectOption('кость')
  await expect(count).toHaveText('Выбрано: 20')
  await row('3021-1').getByRole('checkbox').check()
  await expect(count).toHaveText('Выбрано: 21')
  await row('3002-1').getByRole('checkbox').uncheck()
  await expect(count).toHaveText('Выбрано: 20')
  const resolveCount = state.selectionRequests()
  await page.getByRole('button', { name: 'Следующая страница' }).click()
  await expect(rows).toHaveCount(20)
  await row('3101-1').getByRole('checkbox').check()
  await expect(count).toHaveText('Выбрано: 21')
  await page.getByRole('button', { name: 'Предыдущая страница' }).click()
  await expect(rows).toHaveCount(100)
  await page.getByRole('button', { name: 'Только выбранные', exact: true }).click()
  await expect(rows).toHaveCount(21)
  await page.getByRole('button', { name: 'Все', exact: true }).click()
  await expect(rows).toHaveCount(100)
  await page.getByPlaceholder('№ РЦСМЭ, постановления, в/ч').fill('3021')
  await expect(rows).toHaveCount(1)
  await expect(count).toHaveText('Выбрано: 21')
  await page.getByPlaceholder('№ РЦСМЭ, постановления, в/ч').fill('')
  await expect(rows).toHaveCount(100)
  await page.locator('.protocol-selection-summary').click()
  await expect(page.locator('.protocol-selection-caption')).toHaveText('Диапазон номеров: 3001-1 — 3025-1 · Описание: кость')
  await page.locator('.protocol-selection-summary').click()
  await expect(page.getByPlaceholder('№ рег РЦСМЭ от')).toHaveValue('3001-1')
  await expect(row('3021-1').getByRole('checkbox')).toBeChecked()
  await expect(row('3002-1').getByRole('checkbox')).not.toBeChecked()
  expect(state.selectionRequests()).toBe(resolveCount)
  await expect(page.getByRole('button', { name: 'Скачать список номеров' })).toBeEnabled()
  await page.getByRole('button', { name: 'Сохранить черновик' }).click()
  await expect(page.getByRole('heading', { name: /версия 1/ })).toBeVisible()
  expect(state.saved()?.snapshot.selection).toMatchObject({ rcsme_from: '3001-1', rcsme_to: '3025-1', description: 'кость' })
  await expect(page.locator('.protocol-document-meta output')).toHaveText('21 / 95')
  await page.getByRole('button', { name: 'Сохранённые', exact: true }).click()
  await expect(page.locator('.protocol-list-table tbody tr td').nth(4)).toHaveText('21')
  await page.getByRole('button', { name: state.saved()!.name, exact: true }).click()
  await expect(page.locator('.protocol-selection-summary')).toContainText('21 объектов')
  await page.locator('.protocol-selection-summary').click()
  await expect(page.getByLabel('Описание', { exact: true })).toHaveValue('кость')
  await expect(page.getByPlaceholder('№ рег РЦСМЭ до')).toHaveValue('3025-1')
  await expect(row('3021-1').getByRole('checkbox')).toBeChecked()
  await expect(row('3002-1').getByRole('checkbox')).not.toBeChecked()
  expect(state.selectionRequests()).toBe(resolveCount)
  const expectedNumbers = state.objects.filter((object) => object.id <= 20 && object.id !== 2 || object.id === 21 || object.id === 101).map((object) => object.rcsme_reg_no).join('\n') + '\n'
  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Скачать список номеров' }).click()
  const download = await downloading
  expect(download.suggestedFilename()).toMatch(/_номера\.txt$/)
  expect(await readFile((await download.path())!, 'utf8')).toBe(expectedNumbers)
  await page.locator('.protocol-selection-summary').click()
  await page.screenshot({ path: testInfo.outputPath('selection-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: testInfo.outputPath('selection-mobile.png'), fullPage: true })
  const caption = page.locator('.protocol-selection-caption')
  expect(await caption.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.getByRole('button', { name: 'Предпросмотр печати', exact: true }).click()
  await page.getByRole('button', { name: 'Предпросмотр', exact: true }).click()
  const printCounts = page.locator('.protocol-print-meta > div').filter({ has: page.getByText('Объектов', { exact: true }) }).locator('strong')
  await expect(printCounts).toHaveCount(4)
  expect(await printCounts.allTextContents()).toEqual(['21', '21', '21', '21'])
  await expect(page.locator('.protocol-print-root .protocol-plate-title span').first()).toHaveText('Образцов на плашке: 21')
})

test('custom list без партии восстанавливается без повторного автоматического выбора', async ({ page }) => {
  const state = await fixture(page)
  await page.getByPlaceholder('№ рег РЦСМЭ от').fill('3001-1')
  await page.getByRole('button', { name: 'Вставить список номеров' }).click()
  await page.getByPlaceholder('7600-1\n7601-1\n7602-1').fill('3003-1\n3001-1\n3002-1\n3001-1')
  await page.getByRole('button', { name: 'Применить', exact: true }).click()
  await expect(page.locator('.protocol-selection-actions strong')).toHaveText('Выбрано: 3')
  await expect(page.getByPlaceholder('№ рег РЦСМЭ от')).toHaveCount(0)
  await page.locator('.protocol-object-table tbody tr').filter({ has: page.getByText('3002-1', { exact: true }) }).getByRole('checkbox').uncheck()
  await expect(page.locator('.protocol-selection-actions strong')).toHaveText('Выбрано: 2')
  await expect(page.getByRole('button', { name: 'Скачать список номеров' })).toBeEnabled()
  await page.getByRole('button', { name: 'Сохранить черновик' }).click()
  await expect(page.getByRole('heading', { name: /версия 1/ })).toBeVisible()
  const saved = state.saved()!
  expect(saved.snapshot.selection).toMatchObject({ party_ids: [], rcsme_from: null, rcsme_to: null, numbers: ['3003-1', '3001-1', '3002-1'] })
  const resolveCount = state.selectionRequests()
  const previewCount = state.previewRequests()
  await page.getByRole('button', { name: 'Сохранённые', exact: true }).click()
  await page.getByRole('button', { name: saved.name, exact: true }).click()
  await expect(page.locator('.protocol-selection-summary')).toContainText('2 объектов')
  await expect(page.locator('.protocol-selection-caption')).toHaveText('Список номеров: 3')
  await page.locator('.protocol-selection-summary').click()
  await expect(page.getByRole('button', { name: 'Изменить список номеров' })).toBeVisible()
  await expect(page.locator('.protocol-object-table tbody tr').filter({ has: page.getByText('3002-1', { exact: true }) }).getByRole('checkbox')).not.toBeChecked()
  expect(state.selectionRequests()).toBe(resolveCount)
  expect(state.previewRequests()).toBe(previewCount)
  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Скачать список номеров' }).click()
  expect(await readFile((await (await downloading).path())!, 'utf8')).toBe('3001-1\n3003-1\n')
})

test('запоздавший resolve не заменяет выбор нового диапазона', async ({ page }) => {
  const state = await fixture(page)
  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type=checkbox]').check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await expect(page.locator('.protocol-selection-actions strong')).toHaveText('Выбрано: 120')
  state.delay('3002-1')
  await page.getByPlaceholder('№ рег РЦСМЭ от').fill('3002-1')
  await expect.poll(state.delayedRangeRequested).toBe(true)
  await expect(page.getByRole('button', { name: 'Скачать список номеров' })).toBeDisabled()
  await page.getByPlaceholder('№ рег РЦСМЭ от').fill('3120-1')
  await expect(page.locator('.protocol-selection-actions strong')).toHaveText('Выбрано: 1')
  await expect(page.getByRole('button', { name: 'Скачать список номеров' })).toBeEnabled()
  await page.waitForTimeout(1300)
  await expect(page.locator('.protocol-selection-actions strong')).toHaveText('Выбрано: 1')
})
