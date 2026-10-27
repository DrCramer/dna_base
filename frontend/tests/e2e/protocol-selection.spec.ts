import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { Protocol, ProtocolObject, ProtocolPayload, ProtocolPreview } from '../../src/api/types'
import { protocolNumbers, protocolObjectIds, selectionCaption } from '../../src/components/protocols/protocolSelection'
import { protocolPrintPageCount } from '../../src/components/protocols/ProtocolPrintDocument'
import { paginateDilutionRowHeights } from '../../src/components/protocols/ProtocolDilutionPrintPages'
import { formatRtConcentration, protocolReagentRows } from '../../src/components/protocols/ProtocolSupplementTables'
import { parseTargetConcentration } from '../../src/components/protocols/ProtocolDilutionOptions'
import { dilutionFinalConcentration, dilutionStatus } from '../../src/components/protocols/ProtocolSupplementTables'

test('целевая концентрация принимает запятую и не принимает пустые и нечисловые значения', () => {
  for (const [text, value] of [['0,1', 0.1], ['1', 1], ['1,5', 1.5], ['1.5', 1.5], ['0,2', 0.2], ['0.5', 0.5]] as const) expect(parseTargetConcentration(text)).toBe(value)
  for (const text of ['', ' ', '0', '-1', 'NaN', 'Infinity', '1e999', '.', ',', '1,2,3', '0x10']) expect(parseTargetConcentration(text)).toBeNull()
  const row = { object_id: 1, available: true, source_concentration: 0.4, target_concentration: 1, steps: [] }
  expect(dilutionFinalConcentration(row)).toBe(0.4)
  expect(dilutionStatus(row)).toContain('ниже цели 1')
  expect(dilutionFinalConcentration({ ...row, available: false })).toBeNull()
})

test('концентрации отображаются до четырёх знаков, включая старые snapshot', () => {
  expect(formatRtConcentration(0.81234567)).toBe('0.8123')
  expect(formatRtConcentration(0.63825689)).toBe('0.6383')
  expect(formatRtConcentration(2.2)).toBe('2.2')
  expect(formatRtConcentration(0)).toBe('0')
  expect(formatRtConcentration(null)).toBe('—')
  expect(formatRtConcentration(Infinity)).toBe('—')
})

test('расчёты не подставляют данные другой плашки вместо отсутствующих', () => {
  const components = [{ key: 'mix', label: 'Mix', per_reaction: 5, total: 506 }]
  const preview = { layouts: { pcr: { plates: [{ plate_index: 1 }, { plate_index: 2 }] } }, calculations: { pcr: [{ plate_index: 2, components }], electrophoresis: { components }, electrophoresis_plates: [{ plate_index: 2, components }] } } as unknown as ProtocolPreview
  for (const stage of ['pcr', 'electrophoresis'] as const) {
    expect(protocolReagentRows(preview, stage, 1)).toEqual([])
    expect(protocolReagentRows(preview, stage, 2)).toEqual(components)
  }
})

test('DNA и PCR-продукты показывают объём на реакцию без старых итогов', () => {
  for (const [stage, key] of [['pcr', 'dna'], ['electrophoresis', 'pcr_products']] as const) {
    const components: Array<{ key: string; label: string; per_reaction: number; total: number | null }> = [{ key, label: key, per_reaction: 1, total: 150 }]
    const preview = { layouts: { pcr: { plates: [{ plate_index: 1 }] } }, calculations: { pcr: [{ plate_index: 1, components }], pcr_total: { components }, electrophoresis: { components }, electrophoresis_plates: [{ plate_index: 1, components }] } } as unknown as ProtocolPreview
    expect(protocolReagentRows(preview, stage, 1)).toEqual([{ ...components[0], total: null }])
    expect(protocolReagentRows(preview, stage)).toEqual([{ ...components[0], total: null }])
    expect(components[0].total).toBe(150)
    components[0].total = null
    expect(protocolReagentRows(preview, stage, 1)).toHaveLength(1)
  }
})

test('разведения разбиваются по высоте целых строк без лимита на число объектов', () => {
  expect(paginateDilutionRowHeights([], 600)).toEqual([])
  expect(paginateDilutionRowHeights(Array(96).fill(15), 600)).toEqual([40, 80, 96])
  expect(paginateDilutionRowHeights([20, 35, 10, 25], 60)).toEqual([2, 4])
  expect(paginateDilutionRowHeights([70, 20], 60)).toEqual([1, 2])
  expect(paginateDilutionRowHeights(Array(49).fill(15), 600, 24)).toEqual([24, 48, 49])
})

test('число печатных страниц учитывает только выбранные разделы без аудита округления', () => {
  const preview = {
    layouts: { source: { plates: [{}, {}] }, pcr: { plates: [{}, {}, {}] } },
    dilutions: Array.from({ length: 25 }, (_, index) => ({ object_id: index + 1, steps: [{ dna_volume: 3, water_volume: 65 }], optimization: { enabled: true } })),
    calculations: { pcr: [], pcr_total: { components: [{ key: 'mix', label: 'Mix', per_reaction: 10, total: 250 }] }, electrophoresis: { components: [] } },
  } as unknown as ProtocolPreview
  const view = { hideNoDilution: false, sortKey: null, directions: { first: 'asc' as const, second: 'asc' as const } }
  expect(protocolPrintPageCount(preview, [], view, true, 2)).toBe(2)
  expect(protocolPrintPageCount(preview, [], view, false)).toBe(0)
  expect(protocolPrintPageCount(preview, ['dna_extraction'], view, false)).toBe(2)
  expect(protocolPrintPageCount(preview, ['pcr'], view, false)).toBe(3)
  expect(protocolPrintPageCount(preview, ['pcr'], view, true, 2)).toBe(5)
  expect(protocolPrintPageCount({ ...preview, dilutions: [] }, [], view, true)).toBe(0)
})

test('уникальные ID и TXT используют порядок snapshot, включая старые object_id', () => {
  const objects = [{ id: 2, rcsme_reg_no: 'ии2' }, { object_id: 10, rcsme_reg_no: 'ии10' }, { id: 2, rcsme_reg_no: 'ии2' }, { id: 100, rcsme_reg_no: 'ии100' }]
  expect(protocolObjectIds(objects)).toEqual([2, 10, 100])
  expect(protocolNumbers(objects)).toBe('ии2\nии10\nии100')
  const selection = { case_year: 2026, party_ids: [], rcsme_from: '3001-1', rcsme_to: null, description: null, numbers: [] }
  expect(selectionCaption(selection)).toBe('Диапазон номеров: от 3001-1')
  expect(selectionCaption({ ...selection, rcsme_from: null, rcsme_to: '3020-1' })).toBe('Диапазон номеров: до 3020-1')
})

async function fixture(page: Page, transform: (preview: ProtocolPreview, payload: ProtocolPayload) => ProtocolPreview = (preview) => preview) {
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
    return transform({ selected_count: selected.length, capacity: 95, max_capacity: 96, objects: selected, stages, layouts, calculations, dilutions: [], warnings: [], snapshot: { protocol: payload, objects: selected, stages, layouts, calculations, dilutions: [], warnings: [], selection: payload.selection, plate_rules: payload.plate_rules, dilution_settings: payload.dilution } }, payload)
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

test('слишком большая выборка не запускает preview и позволяет уточнить диапазон', async ({ page }) => {
  await page.route('**/api/protocols/meta?**', (route) => route.fulfill({ json: { protocol_date: new Date().toISOString().slice(0, 10), suggested_no: 1, suggested_name: 'limit-test', max_objects: 50 } }))
  const state = await fixture(page)
  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type=checkbox]').check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await expect(page.locator('.protocol-selection-actions strong')).toHaveText('Выбрано: 120')
  await expect(page.getByText('Выбрано 120 объектов. Максимум в одном протоколе: 50.', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Сохранить черновик' })).toBeDisabled()
  await page.waitForTimeout(700)
  expect(state.previewRequests()).toBe(0)
  await expect(page.locator('.protocol-sheet .protocol-plate-block')).toHaveCount(0)
  await page.getByPlaceholder('№ рег РЦСМЭ до').fill('3020-1')
  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
  expect(state.previewRequests()).toBe(1)
})

test('preview выполняются последовательно и используют последние настройки', async ({ page }) => {
  const state = await fixture(page)
  let active = 0
  let maximumActive = 0
  const names: string[] = []
  let releaseFirst: (() => void) | undefined
  const firstFinished = new Promise<void>((resolve) => { releaseFirst = resolve })
  await page.route('**/api/protocols/preview', async (route) => {
    active++
    maximumActive = Math.max(maximumActive, active)
    names.push((route.request().postDataJSON() as ProtocolPayload).name)
    if (names.length === 1) await firstFinished
    active--
    await route.fallback()
  })
  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type=checkbox]').check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await expect.poll(() => names.length).toBe(1)
  const name = page.locator('.protocol-name-field input')
  await name.fill('intermediate')
  await page.waitForTimeout(500)
  await name.fill('latest')
  await page.waitForTimeout(500)
  expect(names).toHaveLength(1)
  releaseFirst!()
  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
  expect(maximumActive).toBe(1)
  expect(names).toHaveLength(2)
  expect(names[1]).toBe('latest')
  expect(state.previewRequests()).toBe(2)
  await page.waitForTimeout(600)
  expect(names).toHaveLength(2)
})

test('429 не вызывает бесконечный пересчёт и позволяет повторить его вручную', async ({ page }) => {
  const state = await fixture(page)
  let busyRequests = 0
  await page.route('**/api/protocols/preview', async (route) => {
    if (!busyRequests++) await route.fulfill({ status: 429, json: { detail: 'Сервер уже рассчитывает протокол.' } })
    else await route.fallback()
  })
  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type=checkbox]').check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await expect(page.getByRole('button', { name: 'Повторить расчёт' })).toBeEnabled()
  await page.waitForTimeout(700)
  expect(busyRequests).toBe(1)
  await page.getByRole('button', { name: 'Повторить расчёт' }).click()
  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
  expect(state.previewRequests()).toBe(1)
  expect(busyRequests).toBe(2)
})

test('свёрнутые разведения не создают строки таблицы в DOM', async ({ page }) => {
  await fixture(page, (preview) => ({ ...preview, dilutions: preview.objects.map((object) => ({ object_id: object.id, display_name: object.rcsme_reg_no, available: true, steps: [] })) }))
  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type=checkbox]').check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
  const table = page.locator('.protocol-sheet .protocol-dilution-wrap tbody tr')
  await expect(table).toHaveCount(0)
  await page.getByText('Разведения', { exact: true }).click()
  await expect(table).toHaveCount(120)
  await page.locator('.protocol-details-title').click()
  await expect(table).toHaveCount(0)
})

test('24 объекта, крупный шрифт и скрытые столбцы применяются только к печати', async ({ page }, testInfo) => {
  const state = await fixture(page, (preview) => ({ ...preview, dilutions: preview.objects.map((object, index) => ({
    object_id: Number(object.id), display_name: String(object.rcsme_reg_no), plate_index: 1, well: `${'ABCDEFGH'[index % 8]}${1 + Math.floor(index / 8)}`,
    source_concentration: 2.2, target_concentration: 0.1, total_factor: 22, available: true,
    steps: [{ dna_volume: 3, water_volume: 63 + index }, { dna_volume: 10, water_volume: 90 }],
  })) }))
  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type=checkbox]').check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await page.getByPlaceholder('№ рег РЦСМЭ до').fill('3049-1')
  await expect(page.locator('.protocol-selection-actions strong')).toHaveText('Выбрано: 49')
  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
  await page.getByText('Разведения', { exact: true }).click()
  const table = page.locator('.protocol-sheet .protocol-dilution-wrap')
  await expect(table.locator('tbody tr')).toHaveCount(49)
  const requests = state.previewRequests()
  await expect(page.getByLabel('24 объекта на страницу')).not.toBeChecked()
  await page.getByLabel('24 объекта на страницу').check()
  for (const label of ['Плашка', 'Лунка', 'Исх. конц.', 'Кон. конц.', 'Фактор']) await table.getByLabel(`Печатать столбец ${label}`, { exact: true }).uncheck()
  await expect(table.locator('tbody td[data-column=source]').first()).toBeEmpty()
  await expect(table.locator('th[data-column=source]')).toHaveClass(/protocol-dilution-column-hidden/)
  const hiddenBackground = await table.locator('tbody td[data-column=source]').first().evaluate((cell) => getComputedStyle(cell).backgroundColor)
  expect(hiddenBackground).not.toBe('rgba(0, 0, 0, 0)')
  expect(hiddenBackground).not.toBe('rgb(255, 255, 255)')
  await page.getByRole('button', { name: 'Тема: авто' }).click()
  await page.getByRole('button', { name: 'Тема: светлая' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  const darkHiddenBackground = await table.locator('tbody td[data-column=source]').first().evaluate((cell) => getComputedStyle(cell).backgroundColor)
  expect(darkHiddenBackground).not.toBe(hiddenBackground)
  expect(darkHiddenBackground).not.toBe('rgba(0, 0, 0, 0)')
  await page.getByRole('button', { name: 'Тема: тёмная' }).click()
  await expect(table.locator('.protocol-dilution-object').first()).toHaveCSS('text-align', 'right')
  for (const label of ['Объект', 'I разведение', 'II разведение']) await expect(table.getByRole('columnheader', { name: new RegExp(`^${label}`) }).getByRole('checkbox')).toHaveCount(0)
  await table.getByLabel('Печатать столбец Исх. конц.', { exact: true }).check()
  await expect(table.locator('tbody td[data-column=source]').first()).toHaveText('2.2')
  await table.getByLabel('Печатать столбец Исх. конц.', { exact: true }).uncheck()
  await table.screenshot({ path: testInfo.outputPath('dilution-columns-web.png') })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('.protocol-dilution-summary').scrollIntoViewIfNeeded()
  await page.screenshot({ path: testInfo.outputPath('dilution-settings-mobile.png'), fullPage: true })
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.getByRole('button', { name: 'Предпросмотр печати' }).click()
  const selection = page.getByRole('dialog', { name: 'Что печатать', exact: true })
  for (const stage of ['Выделение', 'RT', 'PCR', 'Форез']) await selection.getByLabel(stage, { exact: true }).uncheck()
  await selection.getByRole('button', { name: 'Предпросмотр', exact: true }).click()
  const pages = page.locator('.protocol-print-dilutions-page')
  await expect(pages).toHaveCount(3)
  expect(await pages.evaluateAll((pages) => pages.map((page) => page.querySelectorAll('tbody tr').length))).toEqual([24, 24, 1])
  await expect(pages.first().locator('table')).toHaveCSS('font-size', '12px')
  await expect(pages.locator('thead input')).toHaveCount(0)
  await expect(pages.locator('td[data-column]')).toHaveCount(0)
  await expect(pages.first().locator('tbody td')).toHaveCount(120)
  await expect(pages.first().locator('.protocol-dilution-object').first()).toHaveCSS('text-align', 'right')
  await expect(pages.locator('.protocol-print-page-number')).toHaveText(['Страница 1 из 3', 'Страница 2 из 3', 'Страница 3 из 3'])
  await page.emulateMedia({ media: 'print' })
  await page.evaluate(() => document.body.classList.add('protocol-printing'))
  await page.pdf({ path: testInfo.outputPath('dilutions-24-hidden.pdf'), preferCSSPageSize: true, printBackground: false })
  await pages.first().screenshot({ path: testInfo.outputPath('dilutions-24-hidden.png') })
  expect(await pages.evaluateAll((pages) => pages.every((page) => page.querySelector('tbody tr:last-child')!.getBoundingClientRect().bottom < page.querySelector('footer')!.getBoundingClientRect().top))).toBe(true)
  await page.evaluate(() => document.body.classList.remove('protocol-printing'))
  await page.emulateMedia({ media: 'screen' })
  await page.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await page.getByLabel('24 объекта на страницу').uncheck()
  await page.getByRole('button', { name: 'Предпросмотр печати' }).click()
  await selection.getByRole('button', { name: 'Предпросмотр', exact: true }).click()
  await expect(pages).toHaveCount(2)
  await expect(pages.first().locator('table')).toHaveCSS('font-size', '9px')
  expect(state.previewRequests()).toBe(requests)
})

test('все мишени разделяют источник на два столбца с одинаковой геометрией экран/печать', async ({ page }, testInfo) => {
  test.setTimeout(60_000)
  await fixture(page, (preview, payload) => ({ ...preview, dilutions: preview.objects.map((object, index) => {
    const targets = { long: 0.81234567, small: 0.63825689, y: 0.01429445 }
    const active = payload.dilution.target_overrides?.[`chs:${object.id}`] || 'small'
    return { object_id: Number(object.id), display_name: String(object.rcsme_reg_no), source_kind: 'chs', plate_index: 1, well: `${'ABCDEFGH'[index % 8]}${1 + Math.floor(index / 8)}`, active_target: active, rt_targets: targets, source_concentration: targets[active], target_concentration: 0.1, total_factor: 6.383, available: true, steps: [{ dna_volume: 3, water_volume: 16 }] }
  }) }))
  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type=checkbox]').check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await page.getByPlaceholder('№ рег РЦСМЭ до').fill('3049-1')
  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
  await page.getByText('Разведения', { exact: true }).click()
  await page.getByLabel('Все мишени', { exact: true }).check()
  const table = page.locator('.protocol-sheet .protocol-dilution-wrap table')
  await expect(table.locator('th[data-column=source]')).toHaveAttribute('colspan', '2')
  await expect(table.locator('thead th[data-source-part]')).toHaveText(['Мишень', 'Конц.'])
  const row = table.locator('tbody tr').first()
  await expect(row.locator('td[data-source-part=target] span')).toHaveText(['Long', 'Small', 'Y'])
  await expect(row.locator('td[data-source-part=quantity] > div')).toHaveText(['0.8123', '0.6383', '0.0143'])
  await expect(row.locator('td[data-source-part=quantity] .is-active')).toHaveText('0.6383')
  const targetRowHeights = await row.locator('.protocol-rt-target').evaluateAll((rows) => rows.map((element) => element.getBoundingClientRect().height))
  targetRowHeights.slice(0, 3).forEach((height, index) => expect(Math.abs(height - targetRowHeights[index + 3])).toBeLessThan(0.5))
  await page.getByLabel('Long для 3001-1', { exact: true }).click()
  await expect(row.locator('td[data-source-part=quantity] .is-active')).toHaveText('0.8123')
  await table.getByLabel('Печатать столбец Исх. конц.', { exact: true }).uncheck()
  await expect(table.locator('td[data-source-part]')).toHaveCount(0)
  await expect(table.locator('tbody td[data-column=source]').first()).toBeEmpty()
  await table.getByLabel('Печатать столбец Исх. конц.', { exact: true }).check()
  const webWidths = await row.locator('td').evaluateAll((cells) => cells.map((cell) => cell.getBoundingClientRect().width / cell.closest('table')!.getBoundingClientRect().width))
  await row.scrollIntoViewIfNeeded()
  await page.screenshot({ path: testInfo.outputPath('targets-web.png') })
  await page.locator('main').evaluate((element) => { element.scrollTop = element.scrollHeight })
  const header = page.locator('.protocol-page > .page-header')
  expect((await header.boundingBox())!.y).toBeGreaterThanOrEqual(0)
  expect((await header.boundingBox())!.y).toBeLessThan(2)
  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeVisible()
  await page.getByRole('button', { name: 'Предпросмотр печати' }).click()
  const selection = page.getByRole('dialog', { name: 'Что печатать', exact: true })
  for (const stage of ['Выделение', 'RT', 'PCR', 'Форез']) await selection.getByLabel(stage, { exact: true }).uncheck()
  await selection.getByRole('button', { name: 'Предпросмотр', exact: true }).click()
  const printed = page.locator('.protocol-print-dilutions-page')
  await expect(printed.first()).toBeVisible()
  expect(await printed.count()).toBeGreaterThan(1)
  expect(await printed.locator('tbody tr').count()).toBe(49)
  await expect(printed.first().locator('thead th[data-source-part]')).toHaveText(['Мишень', 'Конц.'])
  await expect(printed.locator('input')).toHaveCount(0)
  for (const article of await printed.all()) {
    const widths = await article.locator('tbody tr').first().locator('td').evaluateAll((cells) => cells.map((cell) => cell.getBoundingClientRect().width / cell.closest('table')!.getBoundingClientRect().width))
    expect(widths).toHaveLength(webWidths.length)
    widths.forEach((width, index) => expect(Math.abs(width - webWidths[index])).toBeLessThan(0.003))
    const heights = await article.locator('tbody tr').first().locator('.protocol-rt-target').evaluateAll((rows) => rows.map((element) => element.getBoundingClientRect().height))
    heights.slice(0, 3).forEach((height, index) => expect(Math.abs(height - heights[index + 3])).toBeLessThan(0.5))
  }
  await page.locator('.protocol-preview-backdrop').evaluate((element) => { element.scrollTop = element.scrollHeight })
  await expect(page.getByRole('button', { name: 'Закрыть', exact: true })).toBeVisible()
  expect((await page.locator('.protocol-preview-toolbar').boundingBox())!.y).toBeGreaterThanOrEqual(0)
  await page.emulateMedia({ media: 'print' })
  await page.evaluate(() => document.body.classList.add('protocol-printing'))
  await page.pdf({ path: testInfo.outputPath('targets.pdf'), preferCSSPageSize: true, printBackground: false })
  await printed.first().screenshot({ path: testInfo.outputPath('targets-print.png') })
  for (const article of await printed.all()) {
    const widths = await article.locator('tbody tr').first().locator('td').evaluateAll((cells) => cells.map((cell) => cell.getBoundingClientRect().width / cell.closest('table')!.getBoundingClientRect().width))
    widths.forEach((width, index) => expect(Math.abs(width - webWidths[index])).toBeLessThan(0.003))
  }
  await page.evaluate(() => document.body.classList.remove('protocol-printing'))
  await page.emulateMedia({ media: 'screen' })
  await page.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await page.getByRole('button', { name: 'Сохранить черновик' }).click()
  await expect(page.getByRole('link', { name: 'Скачать RT', exact: true })).toHaveAttribute('href', /\/protocols\/999001\/excel$/)
  await expect(page.getByRole('link', { name: 'Скачать Excel', exact: true })).toHaveCount(0)
})

test('PCR и ЭФ печатают расчёты своей плашки без общего отдельного листа', async ({ page }, testInfo) => {
  await fixture(page, (preview) => ({ ...preview, calculations: {
    pcr: preview.layouts.pcr.plates.map((plate) => ({ plate_index: plate.plate_index, components: [{ key: 'mix', label: 'Master mix', per_reaction: 5, total: plate.plate_index === 1 ? 506 : 187 }, { key: 'dna', label: 'DNA', per_reaction: 1, total: 150 }] })),
    pcr_total: { components: [{ key: 'mix', label: 'Master mix', per_reaction: 5, total: 693 }, { key: 'dna', label: 'DNA', per_reaction: 1, total: 300 }] },
    electrophoresis: { components: [{ key: 'ils', label: 'ILS', per_reaction: 0.5, total: 81.4 }, { key: 'pcr_products', label: 'PCR-продукты', per_reaction: 1, total: 300 }] },
    electrophoresis_plates: preview.layouts.pcr.plates.map((plate) => ({ plate_index: plate.plate_index, components: [{ key: 'ils', label: 'ILS', per_reaction: 0.5, total: plate.plate_index === 1 ? 54.5 : 27 }, { key: 'pcr_products', label: 'PCR-продукты', per_reaction: 1, total: 150 }] })),
  } }))
  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type=checkbox]').check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await expect(page.locator('.protocol-selection-actions strong')).toHaveText('Выбрано: 120')
  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
  await page.getByText('Расчёты', { exact: true }).click()
  const webCalculations = page.locator('.protocol-sheet .protocol-calculation-columns')
  for (const label of ['DNA', 'PCR-продукты']) {
    const row = webCalculations.getByRole('row').filter({ has: page.getByRole('cell', { name: label, exact: true }) })
    await expect(row.locator('td').nth(1)).toHaveText('1')
    await expect(row.locator('td').nth(2)).toBeEmpty()
  }
  await page.getByRole('button', { name: 'Предпросмотр печати' }).click()
  const selection = page.getByRole('dialog', { name: 'Что печатать', exact: true })
  for (const stage of ['Выделение', 'RT', 'Разведения']) await selection.getByLabel(stage, { exact: true }).uncheck()
  await selection.getByRole('button', { name: 'Предпросмотр', exact: true }).click()
  const pages = page.locator('.protocol-print-page')
  await expect(pages).toHaveCount(4)
  for (let index = 0; index < 4; index++) {
    const calculations = pages.nth(index).locator('.protocol-calculation-columns')
    await expect(calculations.locator('table')).toHaveCount(1)
    await expect(calculations).toContainText(index < 2 ? 'Протокол PCR' : 'Протокол ЭФ')
    await expect(pages.nth(index).locator('.protocol-print-meta > div').last().locator('strong')).toHaveText(index % 2 === 0 ? '95' : '25')
    await expect(pages.nth(index).locator('.protocol-plate-title span')).toHaveText(`Образцов на плашке: ${index % 2 === 0 ? 95 : 25}`)
    await expect(calculations.locator('tbody tr').first().locator('td').last()).toHaveText(['506', '187', '54.5', '27'][index])
    await expect(calculations.locator('tbody tr').last().locator('td').nth(1)).toHaveText('1')
    await expect(calculations.locator('tbody tr').last().locator('td').last()).toBeEmpty()
  }
  await expect(page.locator('.protocol-print-root')).not.toContainText('Расчёты ·')
  await expect(page.locator('.protocol-print-page-number')).toHaveText(Array.from({ length: 4 }, (_, index) => `Страница ${index + 1} из 4`))
  await page.emulateMedia({ media: 'print' })
  await page.evaluate(() => document.body.classList.add('protocol-printing'))
  expect(await pages.evaluateAll((pages) => pages.every((page) => page.querySelector('.protocol-calculation-columns')!.getBoundingClientRect().bottom < page.querySelector('footer')!.getBoundingClientRect().top))).toBe(true)
  await page.pdf({ path: testInfo.outputPath('plate-calculations.pdf'), preferCSSPageSize: true, printBackground: false })
  await pages.first().screenshot({ path: testInfo.outputPath('plate-calculations.png') })
  await page.evaluate(() => document.body.classList.remove('protocol-printing'))
  await page.emulateMedia({ media: 'screen' })
})

for (const { count, longNames } of [{ count: 25, longNames: false }, { count: 96, longNames: false }, { count: 120, longNames: false }, { count: 120, longNames: true }]) {
  test(`печать ${count} разведений${longNames ? ' с длинными номерами' : ''} заполняет A4 по высоте без потери объектов`, async ({ page }, testInfo) => {
    await fixture(page, (preview) => ({ ...preview, dilutions: preview.objects.map((object, index) => ({
      object_id: Number(object.id), display_name: longNames && index % 5 === 0 ? `${object.rcsme_reg_no}-${'1234567890-'.repeat(8)}` : String(object.rcsme_reg_no),
      plate_index: 1 + Math.floor(index / 95), well: `${'ABCDEFGH'[index % 8]}${1 + Math.floor(index / 8) % 12}`,
      source_concentration: 2.2, target_concentration: 0.1, total_factor: 22, available: true,
      steps: [{ dna_volume: 3, water_volume: 63 + index }],
    })) }))
    await page.getByRole('button', { name: 'Партии протокола' }).click()
    await page.locator('.multi-party-modal input[type=checkbox]').check()
    await page.getByRole('button', { name: 'Готово' }).click()
    await page.getByPlaceholder('№ рег РЦСМЭ до').fill(`${3000 + count}-1`)
    await expect(page.locator('.protocol-selection-actions strong')).toHaveText(`Выбрано: ${count}`)
    await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
    await page.getByRole('button', { name: 'Предпросмотр печати' }).click()
    const selection = page.getByRole('dialog', { name: 'Что печатать', exact: true })
    for (const stage of ['Выделение', 'RT', 'PCR', 'Форез']) await selection.getByLabel(stage, { exact: true }).uncheck()
    await selection.getByRole('button', { name: 'Предпросмотр', exact: true }).click()
    const pages = page.locator('.protocol-print-dilutions-page')
    const rows = pages.locator('tbody tr')
    await expect(rows).toHaveCount(count)
    await expect(page.locator('.protocol-print-measure')).toHaveCount(0)
    const pageCount = await pages.count()
    expect(pageCount).toBeLessThanOrEqual(Math.ceil(count / (longNames ? 25 : 30)))
    if (count === 25) expect(pageCount).toBe(1)
    await expect(page.locator('.protocol-preview-toolbar strong')).toContainText(`страниц: ${pageCount}`)
    await expect(pages.locator('.protocol-print-page-number')).toHaveText(Array.from({ length: pageCount }, (_, index) => `Страница ${index + 1} из ${pageCount}`))
    expect(await rows.locator('td:nth-child(3)').allTextContents()).toEqual(Array.from({ length: count }, (_, index) => longNames && index % 5 === 0 ? `${3001 + index}-1-${'1234567890-'.repeat(8)}` : `${3001 + index}-1`))
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(pages).toHaveCount(pageCount)
    await page.setViewportSize({ width: 1280, height: 900 })
    await page.emulateMedia({ media: 'print' })
    await page.evaluate(() => document.body.classList.add('protocol-printing'))
    const geometry = await pages.evaluateAll((pages) => pages.map((page) => {
      const rect = page.getBoundingClientRect()
      const style = getComputedStyle(page)
      const rows = Array.from(page.querySelectorAll('tbody tr')).map((row) => row.getBoundingClientRect())
      const footer = page.querySelector('.protocol-print-page-number')!.getBoundingClientRect()
      return { count: rows.length, first: rows[0].top, last: rows.at(-1)!.bottom, bottom: rect.bottom - parseFloat(style.paddingBottom) - parseFloat(style.borderBottomWidth), firstHeight: rows[0].height, fitsWidth: page.scrollWidth <= page.clientWidth + 1, footerTop: footer.top, footerBottom: footer.bottom, pageBottom: rect.bottom }
    }))
    geometry.forEach((page, index) => {
      expect(page.last).toBeLessThanOrEqual(page.bottom + 1)
      expect(page.fitsWidth).toBe(true)
      expect(page.footerTop).toBeGreaterThan(page.last)
      expect(page.footerBottom).toBeLessThan(page.pageBottom)
      if (index < geometry.length - 1) expect(page.bottom - page.last).toBeLessThanOrEqual(geometry[index + 1].firstHeight + 3)
    })
    await page.pdf({ path: testInfo.outputPath(`dilutions-${count}.pdf`), preferCSSPageSize: true, printBackground: false })
    await pages.first().screenshot({ path: testInfo.outputPath(`dilutions-${count}.png`) })
    await page.evaluate(() => document.body.classList.remove('protocol-printing'))
    await page.emulateMedia({ media: 'screen' })
  })
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

test('удобные объёмы воды сохраняют лунки, настройки и значения печати', async ({ page }, testInfo) => {
  test.setTimeout(60_000)
  const state = await fixture(page, (preview, payload) => {
    const enabled = payload.dilution.optimize_water_volumes ?? false
    const rows = preview.objects.map((object) => {
      const index = Number(object.id) - 1
      const minimum = payload.dilution.minimum_final_volume_enabled
      const source = index < 5 ? (66 + index) / 30 : index === 5 ? 0.2 : index === 6 ? 1000 : null
      const baseline = index < 5 ? [{ dna_volume: 3, water_volume: 63 + index }] : index === 5 ? [{ dna_volume: minimum ? 8 : 3, water_volume: minimum ? 8 : 3 }] : index === 6 ? [{ dna_volume: 3, water_volume: 297 }, { dna_volume: 10, water_volume: 990 }] : []
      const steps = baseline.map((step) => ({ ...step, water_volume: enabled && index < 5 ? 65 : step.water_volume }))
      const well = preview.layouts.pcr.plates.flatMap((plate) => plate.wells).find((well) => well.object_id === object.id)
      const actual = steps.reduce((concentration, step) => concentration * step.dna_volume / (step.dna_volume + step.water_volume), source || 0)
      const before = baseline.reduce((concentration, step) => concentration * step.dna_volume / (step.dna_volume + step.water_volume), source || 0)
      const changed = steps.some((step, index) => step.water_volume !== baseline[index].water_volume)
      return { object_id: Number(object.id), display_name: String(object.rcsme_reg_no), plate_index: well?.plate_index || null, well: well?.well || null, source_concentration: source, target_concentration: 0.1, total_factor: source ? source / 0.1 : null, available: source !== null, steps,
        ...(enabled && source !== null ? { baseline_steps: baseline, optimization: { enabled: true, status: changed ? 'optimized' as const : 'unchanged' as const, needs_review: false, actual_final_concentration: actual, relative_error_percent: 100 * (actual / 0.1 - 1), target_concentration: 0.1, baseline_actual_final_concentration: before, baseline_relative_error_percent: 100 * (before / 0.1 - 1), baseline_out_of_tolerance: false, reason: null, reason_code: null, first_dilution_remaining_volume: index === 6 ? 290 : null } } : {}) }
    })
    const groups = (step: number) => {
      const volumes = Array.from(new Set(rows.flatMap((row) => row.steps[step] ? [row.steps[step].water_volume] : []))).sort((a, b) => a - b)
      return volumes.map((water_volume) => {
        const objects = rows.filter((row) => row.steps[step]?.water_volume === water_volume).map((row) => ({ object_id: row.object_id, display_name: row.display_name, plate_index: row.plate_index, well: row.well, needs_review: false }))
        return { water_volume, object_count: objects.length, objects }
      })
    }
    const summary = enabled ? { enabled: true, object_count: rows.length, active_object_count: Math.min(7, rows.length), unique_water_volumes_before: new Set(rows.flatMap((row) => (row.baseline_steps || []).map((step) => step.water_volume))).size, unique_water_volumes_after: new Set(rows.flatMap((row) => row.steps.map((step) => step.water_volume))).size, optimized_object_count: rows.filter((row) => row.optimization?.status === 'optimized').length, unchanged_object_count: rows.filter((row) => row.optimization?.status === 'unchanged').length, blocked_object_count: 0, excluded_object_count: Math.max(0, rows.length - 7), max_absolute_error_percent: Math.max(0, ...rows.map((row) => Math.abs(row.optimization?.relative_error_percent || 0))), batch_groups_first: groups(0), batch_groups_second: groups(1) } : null
    const calculations = { pcr: [{ components: [{ key: 'mix', label: 'Mix', per_reaction: 10, total: 70 }] }], electrophoresis: { components: [{ key: 'ils', label: 'ILS', per_reaction: 1, total: 7 }] } }
    return { ...preview, calculations, dilutions: rows, dilution_optimization: summary, snapshot: { ...preview.snapshot, calculations, dilutions: rows, dilution_optimization: summary } }
  })
  await page.getByRole('button', { name: 'Партии протокола' }).click()
  await page.locator('.multi-party-modal input[type=checkbox]').check()
  await page.getByRole('button', { name: 'Готово' }).click()
  await page.getByPlaceholder('№ рег РЦСМЭ от').fill('3001-1')
  await page.getByPlaceholder('№ рег РЦСМЭ до').fill('3007-1')
  await expect(page.locator('.protocol-selection-actions strong')).toHaveText('Выбрано: 7')
  await expect(page.getByLabel('Округление объема H₂O')).not.toBeChecked()
  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
  const gridBefore = await page.locator('.protocol-sheet .protocol-well span').allTextContents()
  await page.getByLabel('Округление объема H₂O').check()
  await page.getByText('Разведения', { exact: true }).click()
  await expect(page.locator('.protocol-water-summary')).toContainText('8 → 4')
  await expect(page.locator('.protocol-water-summary')).toContainText('4 из 7 объектов')
  expect(await page.locator('.protocol-sheet .protocol-well span').allTextContents()).toEqual(gridBefore)
  const dilutionRows = page.locator('.protocol-sheet .protocol-dilution-wrap tbody tr')
  const first = dilutionRows.filter({ hasText: '3001-1' })
  await expect(first.locator('td').nth(7)).toHaveText('65')
  await expect(first.locator('td').nth(7)).toHaveAttribute('title', /До округления: 63 мкл\nДля работы: 65 мкл\nРасчётная концентрация:/)
  await expect(first.locator('td').nth(4)).toHaveText('0.1')
  const coordinates = await first.locator('td').allTextContents()
  await page.getByText('Настройки округления', { exact: true }).click()
  await expect(page.getByLabel('Допуск концентрации, %')).toHaveValue('5')
  await page.getByLabel('Предпочтительный шаг воды, мкл').selectOption('5')
  await page.getByText('Ограничения дозирования', { exact: true }).click()
  await page.getByLabel('Дискретность H₂O, мкл').pressSequentially('0.1')
  await expect(page.getByLabel('Дискретность H₂O, мкл')).toHaveValue('0.1')
  await expect(page.getByRole('button', { name: 'Предпросмотр печати' })).toBeEnabled()
  await page.getByLabel('Минимальный объём 15 мкл').check()
  await expect(dilutionRows.filter({ hasText: '3006-1' }).locator('td').nth(6)).toHaveText('8')
  await expect(dilutionRows.filter({ hasText: '3006-1' }).locator('td').nth(7)).toHaveText('8')
  await page.locator('.protocol-sheet .protocol-dilution-sort').first().click()
  await expect(dilutionRows.first()).toContainText('3006-1')
  expect((await first.locator('td').allTextContents()).slice(0, 3)).toEqual(coordinates.slice(0, 3))
  await page.getByText('Подробности округления', { exact: true }).click()
  await expect(page.getByText('65 мкл — 5 объектов', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('water-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: testInfo.outputPath('water-mobile.png'), fullPage: true })
  await page.setViewportSize({ width: 1280, height: 900 })
  await expect(page.getByRole('button', { name: 'Сохранить черновик' })).toBeEnabled()
  await page.getByRole('button', { name: 'Сохранить черновик' }).click()
  await expect(page.getByRole('heading', { name: /версия 1/ })).toBeVisible()
  const saved = state.saved()!
  expect(saved.snapshot.dilution_settings).toMatchObject({ optimize_water_volumes: true, minimum_final_volume_enabled: true, preferred_water_step_ul: 5, allowed_concentration_error_percent: 5 })
  expect((saved.snapshot.dilution_settings as ProtocolPayload['dilution']).pipetting).toMatchObject({ water_increment_ul: 0.1 })
  await page.getByRole('button', { name: 'Сохранённые', exact: true }).click()
  await page.getByRole('button', { name: saved.name, exact: true }).click()
  await expect(page.getByLabel('Округление объема H₂O')).toBeChecked()
  await page.getByText('Разведения', { exact: true }).click()
  await expect(first.locator('td').nth(7)).toHaveText('65')
  const working = await dilutionRows.evaluateAll((rows) => rows.map((row) => [row.children[2].textContent, row.children[6].textContent, row.children[7].textContent, row.children[8].textContent, row.children[9].textContent]))
  await page.getByRole('button', { name: 'Предпросмотр печати', exact: true }).click()
  await page.getByRole('button', { name: 'Предпросмотр', exact: true }).click()
  const printRows = page.locator('.protocol-print-root .protocol-dilution-wrap tbody tr')
  const printed = await printRows.evaluateAll((rows) => rows.map((row) => [row.children[2].textContent, row.children[6].textContent, row.children[7].textContent, row.children[8].textContent, row.children[9].textContent]))
  expect(printed).toEqual(working)
  await expect(page.locator('.protocol-print-root .protocol-dilution-audit')).toHaveCount(0)
  await expect(page.locator('.protocol-print-root')).not.toContainText('Округление разведений')
  await expect(page.locator('.protocol-print-page')).toHaveCount(5)
  await expect(page.locator('.protocol-print-page-number')).toHaveText(Array.from({ length: 5 }, (_, index) => `Страница ${index + 1} из 5`))
  await expect(page.locator('.protocol-print-root .protocol-dilution-options')).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('water-print.png'), fullPage: true })
  await page.locator('.protocol-print-data-page').filter({ has: page.getByRole('heading', { name: /^Разведения ·/ }) }).screenshot({ path: testInfo.outputPath('water-dilutions.png') })
  expect(await page.locator('.protocol-print-page').evaluateAll((pages) => pages.every((page) => page.scrollWidth <= page.clientWidth + 1))).toBe(true)
  await page.emulateMedia({ media: 'print' })
  await page.evaluate(() => document.body.classList.add('protocol-printing'))
  await page.pdf({ path: testInfo.outputPath('numbered-stages-dilutions-calculations.pdf'), preferCSSPageSize: true, printBackground: false })
  await page.evaluate(() => document.body.classList.remove('protocol-printing'))
  await page.emulateMedia({ media: 'screen' })
  await page.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await page.getByRole('button', { name: 'Предпросмотр печати', exact: true }).click()
  const selection = page.getByRole('dialog', { name: 'Что печатать', exact: true })
  for (const stage of ['Выделение', 'RT', 'PCR', 'Форез']) await selection.getByLabel(stage, { exact: true }).uncheck()
  await expect(selection.getByLabel('Разведения', { exact: true })).toBeChecked()
  await selection.getByRole('button', { name: 'Предпросмотр', exact: true }).click()
  await expect(page.locator('.protocol-print-page')).toHaveCount(1)
  await expect(page.locator('.protocol-print-page-number')).toHaveText('Страница 1 из 1')
  await expect(page.locator('.protocol-preview-toolbar strong')).toContainText('страниц: 1')
  await expect(page.locator('.protocol-print-root .protocol-calculation-columns')).toHaveCount(0)
  expect(await printRows.evaluateAll((rows) => rows.map((row) => [row.children[2].textContent, row.children[6].textContent, row.children[7].textContent, row.children[8].textContent, row.children[9].textContent]))).toEqual(working)
  await printRows.nth(1).locator('td').first().hover()
  await page.emulateMedia({ media: 'print' })
  await page.evaluate(() => document.body.classList.add('protocol-printing'))
  await expect(printRows.first().locator('td').first()).toHaveCSS('background-color', 'rgb(255, 255, 255)')
  await expect(printRows.nth(1).locator('td').first()).toHaveCSS('background-color', 'rgb(230, 230, 230)')
  await expect(printRows.nth(1).locator('td').first()).toHaveCSS('print-color-adjust', 'exact')
  await page.pdf({ path: testInfo.outputPath('dilutions-no-background.pdf'), preferCSSPageSize: true, printBackground: false })
  await page.screenshot({ path: testInfo.outputPath('dilutions-print-media.png'), fullPage: true })
  await page.evaluate(() => document.body.classList.remove('protocol-printing'))
  await page.emulateMedia({ media: 'screen' })
  await page.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await page.getByRole('button', { name: 'Предпросмотр печати', exact: true }).click()
  await selection.getByLabel('Разведения', { exact: true }).uncheck()
  await expect(selection.getByRole('button', { name: 'Предпросмотр', exact: true })).toBeDisabled()
  await selection.getByLabel('PCR', { exact: true }).check()
  await selection.getByRole('button', { name: 'Предпросмотр', exact: true }).click()
  await expect(page.locator('.protocol-print-page')).toHaveCount(1)
  await expect(page.locator('.protocol-print-page-number')).toHaveText('Страница 1 из 1')
  await expect(page.locator('.protocol-preview-toolbar strong')).toContainText('страниц: 1')
  await expect(printRows).toHaveCount(0)
  await expect(page.locator('.protocol-print-root .protocol-dilution-audit')).toHaveCount(0)
  await expect(page.locator('.protocol-print-root .protocol-calculation-columns')).toContainText('Протокол PCR')
  await expect(page.locator('.protocol-print-root .protocol-calculation-columns')).not.toContainText('Протокол ЭФ')
})
