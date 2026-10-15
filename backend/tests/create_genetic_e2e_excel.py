"""Generate a small, non-sensitive workbook for real browser import tests."""
import sys
from openpyxl import Workbook


workbook = Workbook()
source = workbook.active
source.title = "Единая_плашка_A4"
source["A2"], source["B2"] = "Дата", "14.10.2026"
source["F2"], source["G2"] = "Название", "Excel E2E"
source["B4"], source["B5"], source["B6"] = "14.10.2026", "Неизвестный набор", "Неизвестный исполнитель"
source["A10"], source["B10"], source["C10"] = "A", "ExcelEX-1", "ExcelEX-2"
pcr = workbook.create_sheet("PCR")
pcr["A18"], pcr["B18"] = "A", "L1"
pcr["A19"], pcr["B19"] = "B", "ExcelEX-2"
pcr["A25"], pcr["M25"] = "H", "ExcelEX-1"
workbook.save(sys.argv[1])
