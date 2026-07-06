import * as XLSX from 'xlsx'

// Builds an .xlsx with one sheet per {name, rows} entry (rows[0] = headers)
// and triggers a browser download. Runs entirely client-side — no backend
// round-trip, since every dashboard already has this data loaded to render
// the page the user is looking at.
export function exportXlsx(filename, sheets) {
  const wb = XLSX.utils.book_new()
  for (const { name, rows } of sheets) {
    const ws = XLSX.utils.aoa_to_sheet(rows)
    XLSX.utils.book_append_sheet(wb, ws, name.slice(0, 31)) // Excel sheet-name limit
  }
  XLSX.writeFile(wb, filename)
}
