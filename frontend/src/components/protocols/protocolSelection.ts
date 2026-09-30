import type { ProtocolSelectionSettings } from '../../api/types'

export function protocolObjectIds(objects: Array<Record<string, unknown>>): number[] {
  return Array.from(new Set(objects.flatMap((item) => {
    const id = item.id ?? item.object_id
    return typeof id === 'number' ? [id] : []
  })))
}

export function protocolNumbers(objects: Array<Record<string, unknown>>): string {
  const seen = new Set<number>()
  return objects.flatMap((item) => {
    const id = item.id ?? item.object_id
    if (typeof id !== 'number' || seen.has(id)) return []
    seen.add(id)
    return typeof item.rcsme_reg_no === 'string' && item.rcsme_reg_no.trim() ? [item.rcsme_reg_no.trim()] : []
  }).join('\n')
}

export function selectionRangeError(selection: ProtocolSelectionSettings): boolean {
  const pattern = /^\d+(?:-\d+)?$/
  return [selection.rcsme_from, selection.rcsme_to].some((value) => Boolean(value?.trim() && !pattern.test(value.trim())))
}

export function selectionFilters(selection: ProtocolSelectionSettings) {
  return {
    caseYear: selection.case_year ?? undefined,
    partyIds: selection.party_ids,
    rcsmeFrom: selection.rcsme_from?.trim() || undefined,
    rcsmeTo: selection.rcsme_to?.trim() || undefined,
    description: selection.description || undefined,
    numbers: selection.numbers.length ? selection.numbers : undefined
  }
}

export function selectionCaption(selection: ProtocolSelectionSettings): string {
  const from = selection.rcsme_from?.trim()
  const to = selection.rcsme_to?.trim()
  const range = from && to ? `${from} — ${to}` : from ? `от ${from}` : to ? `до ${to}` : ''
  return [range ? `Диапазон номеров: ${range}` : '', selection.description ? `Описание: ${selection.description}` : '', selection.numbers.length ? `Список номеров: ${selection.numbers.length}` : ''].filter(Boolean).join(' · ')
}
