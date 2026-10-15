import type { ProtocolKind } from '../../api/types'

export function ProtocolSourceTabs({ kind, disabled, onChange }: { kind: ProtocolKind; disabled?: boolean; onChange: (kind: ProtocolKind) => void }) {
  return <div className="protocol-source-tabs" role="tablist" aria-label="Вид протокола">
    {([['chs', 'ЧС'], ['genetic_examination', 'Генетические экспертизы']] as const).map(([value, label]) => <button type="button" role="tab" aria-selected={kind === value} disabled={disabled} key={value} className={kind === value ? 'active' : ''} onClick={() => onChange(value)}>{label}</button>)}
  </div>
}
