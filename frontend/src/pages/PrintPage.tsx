export function PrintPage() {
  return (
    <div className="page print-page" aria-label="Печать DOCX">
      <div className="print-frame-wrap">
        <iframe
          title="Печать DOCX"
          src="/print?embedded=1"
          className="print-frame"
        />
      </div>
    </div>
  )
}
