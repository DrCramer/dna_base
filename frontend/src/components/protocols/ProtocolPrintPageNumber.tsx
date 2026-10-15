export function ProtocolPrintPageNumber({ page, total }: { page: number; total: number }) {
  return <footer className="protocol-print-page-number">Страница {page} из {total}</footer>
}
