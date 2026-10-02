"""Builds a live Excel dashboard: ratios are formulas on the Data sheet, the Dashboard has company and
year dropdowns, and thresholds are editable. Everything recalculates in Excel without Python."""
import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .schema import ALL_COLUMNS, LABELS

FONT = "Arial"
INK = "0B1F3A"
INDIGO = "0B1F3A"
THIN = Side(style="thin", color="D4D4E4")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", start_color=INDIGO)
INPUT_FILL = PatternFill("solid", start_color="FFF2CC")
SOFT_FILL = PatternFill("solid", start_color="F6F0E4")
NUMBER_FORMATS = {"x": '0.00"x";-0.00"x"', "%": "0.0%", "days": '0" days"'}
RAG_FILLS = {"Green": "C6EFCE", "Amber": "FFE699", "Red": "F4B6B6"}


def _header(ws, row, first_col, last_col):
    for col in range(first_col, last_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER


class ExcelDashboard:
    def __init__(self, data, ratios, focal_company, year, industry, source_label,
                 issues, fixes, recommendations, summary_line, macro_tables=None):
        self.data = data.sort_values(["company", "year"]).reset_index(drop=True)
        self.ratios = ratios
        self.companies = sorted(self.data["company"].unique())
        self.years = sorted(self.data["year"].unique())
        self.focal, self.year, self.industry = focal_company, year, industry
        self.source_label = source_label
        self.issues, self.fixes = issues, fixes
        self.recommendations, self.summary_line = recommendations, summary_line
        self.macro_tables = macro_tables or {}       # {"Macro path": df, "GDP betas": df, ...}
        self.wb = Workbook()
        self.data_cols, self.ratio_cols, self.threshold_rows = {}, {}, {}

    def to_bytes(self):
        dashboard = self.wb.active
        dashboard.title = "Dashboard"
        self._data_sheet()
        self._thresholds_sheet()
        self._ratios_sheet()
        self._dashboard(dashboard)
        self._validation_sheet()
        self._macro_sheet()
        self._notes_sheet()
        for ws in self.wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.font.name != FONT:
                        f = cell.font
                        cell.font = Font(name=FONT, bold=f.bold, italic=f.italic, size=f.size, color=f.color)
        buffer = io.BytesIO()
        self.wb.save(buffer)
        return buffer.getvalue()

    # ---------- sheets ----------
    def _data_sheet(self):
        ws = self.wb.create_sheet("Data")
        for j, col in enumerate(ALL_COLUMNS, 1):
            ws.cell(row=1, column=j, value=LABELS.get(col, col.title()))
            self.data_cols[col] = get_column_letter(j)
        _header(ws, 1, 1, len(ALL_COLUMNS))
        for i, record in enumerate(self.data[ALL_COLUMNS].itertuples(index=False), 2):
            for j, value in enumerate(record, 1):
                value = None if (isinstance(value, float) and pd.isna(value)) else value
                cell = ws.cell(row=i, column=j, value=value)
                cell.font = Font(name=FONT, color="0000FF")
                if j > 3:
                    cell.number_format = '#,##0.0;(#,##0.0);"-"'
        ws.freeze_panes = "D2"
        ws.column_dimensions["A"].width = 30
        for j in range(2, len(ALL_COLUMNS) + 1):
            ws.column_dimensions[get_column_letter(j)].width = 13
        ws.cell(row=len(self.data) + 3, column=1,
                value=f"₹ crore. Source: {self.source_label}. Blue = input values; blank = not reported.")

    def _thresholds_sheet(self):
        ws = self.wb.create_sheet("Thresholds")
        headers = ["Key", "Ratio", "Category", "Higher is better?", "Green cut-off", "Amber cut-off", "Unit"]
        for j, h in enumerate(headers, 1):
            ws.cell(row=1, column=j, value=h)
        _header(ws, 1, 1, len(headers))
        for i, ratio in enumerate(self.ratios, 2):
            values = [ratio.key, ratio.name, ratio.category, "Yes" if ratio.higher_is_better else "No",
                      ratio.green, ratio.amber, ratio.unit]
            for j, v in enumerate(values, 1):
                cell = ws.cell(row=i, column=j, value=v)
                cell.border = BORDER
                if j in (5, 6):
                    cell.font, cell.fill = Font(name=FONT, color="0000FF"), INPUT_FILL
                    cell.number_format = NUMBER_FORMATS[ratio.unit]
            self.threshold_rows[ratio.key] = i
        ws.cell(row=len(self.ratios) + 3, column=1,
                value="Yellow cells are editable. Cut-offs are cross-industry rules of thumb (an assumption); "
                      "tighten or loosen them for your industry and the Dashboard status updates.")
        for col, width in zip("ABCDEFG", [22, 30, 16, 16, 14, 14, 8], strict=True):
            ws.column_dimensions[col].width = width

    def _ratios_sheet(self):
        ws = self.wb.create_sheet("Ratios")
        headers = ["Key", "Company", "Year"] + [r.name for r in self.ratios]
        for j, h in enumerate(headers, 1):
            ws.cell(row=1, column=j, value=h)
        _header(ws, 1, 1, len(headers))
        ws.row_dimensions[1].height = 42
        dc, n = self.data_cols, len(self.data)
        for r in range(2, n + 2):
            ws.cell(row=r, column=1, value=f'=Data!{dc["company"]}{r}&"|"&Data!{dc["year"]}{r}')
            ws.cell(row=r, column=2, value=f"=Data!{dc['company']}{r}")
            ws.cell(row=r, column=3, value=f"=Data!{dc['year']}{r}")
            for j, ratio in enumerate(self.ratios, 4):
                cell = ws.cell(row=r, column=j, value=ratio.excel_formula(dc, r))
                cell.number_format, cell.border = NUMBER_FORMATS[ratio.unit], BORDER
        for j, ratio in enumerate(self.ratios, 4):
            letter = get_column_letter(j)
            self.ratio_cols[ratio.key] = letter
            ws.column_dimensions[letter].width = 13
            self._rag_rules(ws, f"{letter}2:{letter}{n + 1}", f"{letter}2", ratio)
        ws.column_dimensions["A"].width = 34
        ws.column_dimensions["B"].width = 28
        ws.freeze_panes = "D2"

    def _rag_rules(self, ws, cell_range, first_cell, ratio):
        t = self.threshold_rows[ratio.key]
        op = ">=" if ratio.higher_is_better else "<="
        for status, formula in (
                ("Green", f"AND(ISNUMBER({first_cell}),{first_cell}{op}Thresholds!$E${t})"),
                ("Amber", f"AND(ISNUMBER({first_cell}),{first_cell}{op}Thresholds!$F${t})"),
                ("Red", f"ISNUMBER({first_cell})")):
            ws.conditional_formatting.add(cell_range, FormulaRule(
                formula=[formula], fill=PatternFill("solid", start_color=RAG_FILLS[status]), stopIfTrue=True))

    def _lookup(self, ratio_key, company_ref, year_ref):
        col = self.ratio_cols[ratio_key]
        return f'=IFERROR(INDEX(Ratios!${col}:${col},MATCH({company_ref}&"|"&{year_ref},Ratios!$A:$A,0)),"")'

    def _dashboard(self, ws):
        ws.sheet_view.showGridLines = False
        n_co = len(self.companies)
        first_co, last_co = 4, 3 + n_co
        median_col, focal_col, status_col = last_co + 1, last_co + 2, last_co + 3
        ws.column_dimensions["A"].width = 2
        ws.column_dimensions["B"].width = 28
        ws.column_dimensions["C"].width = 15
        for j in range(first_co, status_col + 1):
            ws.column_dimensions[get_column_letter(j)].width = 15

        ws["B1"] = f"Peer health dashboard: {self.industry}"
        ws["B1"].font = Font(name=FONT, size=18, bold=True, color=INK)
        ws["B2"] = f"Source: {self.source_label}. Figures in ₹ crore. Ratios are live formulas."
        ws["B2"].font = Font(name=FONT, italic=True, color="7A7A99")

        ws["B4"], ws["B5"] = "Focal company", "Financial year"
        ws["C4"], ws["C5"] = self.focal, self.year
        for ref in ("C4", "C5"):
            ws[ref].fill, ws[ref].border = INPUT_FILL, BORDER
            ws[ref].font = Font(name=FONT, bold=True, color="0000FF")
        ws.merge_cells("C4:E4")
        ws.merge_cells("C5:E5")
        lists = self.wb.create_sheet("Lists")
        lists.sheet_state = "hidden"
        for col, (values, ref) in enumerate(((self.companies, "C4"), (self.years, "C5")), 1):
            for i, value in enumerate(values, 1):
                lists.cell(row=i, column=col, value=value)
            letter = get_column_letter(col)
            dv = DataValidation(type="list", formula1=f"=Lists!${letter}$1:${letter}${len(values)}")
            ws.add_data_validation(dv)
            dv.add(ref)
        ws["G4"] = "Change the yellow cells; every figure below recalculates."
        ws["G4"].font = Font(name=FONT, italic=True, size=9, color="7A7A99")

        # KPI cards
        kpis = [("roce", "ROCE"), ("ebitda_margin", "EBITDA margin"),
                ("net_debt_to_ebitda", "Net debt / EBITDA"), ("roe", "ROE")]
        for idx, (key, label) in enumerate(kpis):
            col = get_column_letter(2 + idx * 2)
            nxt = get_column_letter(3 + idx * 2)
            ws.merge_cells(f"{col}7:{nxt}7")
            ws.merge_cells(f"{col}8:{nxt}8")
            ws[f"{col}7"] = label
            ws[f"{col}7"].font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
            ws[f"{col}7"].fill = HEADER_FILL
            ws[f"{col}7"].alignment = Alignment(horizontal="center")
            ws[f"{col}8"] = self._lookup(key, "$C$4", "$C$5")
            ws[f"{col}8"].font = Font(name=FONT, bold=True, size=20, color=INK)
            ws[f"{col}8"].number_format = NUMBER_FORMATS[next(r.unit for r in self.ratios if r.key == key)]
            ws[f"{col}8"].alignment = Alignment(horizontal="center", vertical="center")
            ws[f"{col}8"].fill = SOFT_FILL
        ws.row_dimensions[8].height = 38

        # Peer table
        top = 11
        ws.cell(row=top - 1, column=2, value="Peer comparison for the selected year").font = \
            Font(name=FONT, bold=True, size=12, color=INK)
        for j, h in enumerate(["Ratio", "Category"] + self.companies + ["Peer median", "Focal value", "Status"], 2):
            ws.cell(row=top, column=j, value=h)
        _header(ws, top, 2, status_col)
        ws.row_dimensions[top].height = 44
        for i, ratio in enumerate(self.ratios, top + 1):
            ws.cell(row=i, column=2, value=ratio.name)
            ws.cell(row=i, column=3, value=ratio.category)
            for j in range(first_co, last_co + 1):
                ws.cell(row=i, column=j, value=self._lookup(ratio.key, f"{get_column_letter(j)}${top}", "$C$5"))
            lo, hi = get_column_letter(first_co), get_column_letter(last_co)
            ws.cell(row=i, column=median_col, value=f'=IFERROR(MEDIAN({lo}{i}:{hi}{i}),"")')
            ws.cell(row=i, column=focal_col, value=self._lookup(ratio.key, "$C$4", "$C$5"))
            t, v = self.threshold_rows[ratio.key], f"{get_column_letter(focal_col)}{i}"
            ws.cell(row=i, column=status_col, value=(
                f'=IF({v}="","n/a",IF(Thresholds!$D${t}="Yes",'
                f'IF({v}>=Thresholds!$E${t},"Green",IF({v}>=Thresholds!$F${t},"Amber","Red")),'
                f'IF({v}<=Thresholds!$E${t},"Green",IF({v}<=Thresholds!$F${t},"Amber","Red"))))'))
            for j in range(2, status_col + 1):
                cell = ws.cell(row=i, column=j)
                cell.border = BORDER
                if first_co <= j <= focal_col:
                    cell.number_format = NUMBER_FORMATS[ratio.unit]
            ws.cell(row=i, column=status_col).alignment = Alignment(horizontal="center")
        last_row = top + len(self.ratios)
        s = get_column_letter(status_col)
        for status, color in RAG_FILLS.items():
            ws.conditional_formatting.add(f"{s}{top + 1}:{s}{last_row}", CellIsRule(
                operator="equal", formula=[f'"{status}"'], fill=PatternFill("solid", start_color=color)))
        for j in range(first_co, last_co + 1):
            col = get_column_letter(j)
            ws.conditional_formatting.add(f"{col}{top + 1}:{col}{last_row}", FormulaRule(
                formula=[f"{col}${top}=$C$4"], font=Font(bold=True, color=INDIGO), fill=SOFT_FILL))

        # Notes from the app
        notes = last_row + 2
        ws.cell(row=notes, column=2, value="Analyst notes from PeerLens").font = Font(name=FONT, bold=True, size=12, color=INK)
        ws.cell(row=notes + 1, column=2, value=f"Written for {self.focal}, {self.year} at export time.").font = \
            Font(name=FONT, italic=True, size=9, color="7A7A99")
        ws.cell(row=notes + 2, column=2, value=self.summary_line).font = Font(name=FONT, bold=True)
        for k, rec in enumerate(self.recommendations, notes + 3):
            ws.merge_cells(start_row=k, start_column=2, end_row=k, end_column=status_col)
            cell = ws.cell(row=k, column=2, value=f"[{rec['status']}] {rec['ratio']}: {rec['text']}")
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[k].height = 34

        # Trend blocks and charts
        trend_top = notes + 3 + len(self.recommendations) + 2
        self._trend_block(ws, trend_top, "roce", "ROCE by year")
        second = trend_top + len(self.years) + 3
        self._trend_block(ws, second, "net_debt_to_ebitda", "Net debt / EBITDA by year")
        chart_row = second + len(self.years) + 3
        ws.add_chart(self._line_chart(ws, trend_top, "ROCE", "0%"), f"B{chart_row}")
        ws.add_chart(self._line_chart(ws, second, "Net debt / EBITDA (x)", "0.0"), f"{get_column_letter(first_co + 2)}{chart_row}")

        bar = BarChart()
        bar.type, bar.title, bar.legend = "bar", "ROCE by company, selected year", None
        bar.x_axis.title, bar.y_axis.numFmt = None, "0%"
        roce_row = top + 1 + [r.key for r in self.ratios].index("roce")
        bar.add_data(Reference(ws, min_col=first_co, max_col=last_co, min_row=roce_row), from_rows=True)
        bar.set_categories(Reference(ws, min_col=first_co, max_col=last_co, min_row=top))
        bar.height, bar.width = 7.5, 13
        ws.add_chart(bar, f"{get_column_letter(status_col + 2)}{top}")

        ws.freeze_panes = "A6"
        ws.page_setup.orientation = "landscape"
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0

    def _trend_block(self, ws, top, key, title):
        unit = next(r.unit for r in self.ratios if r.key == key)
        ws.cell(row=top - 1, column=2, value=title).font = Font(name=FONT, bold=True, color=INK)
        ws.cell(row=top, column=2, value="Year")
        for j, company in enumerate(self.companies, 3):
            ws.cell(row=top, column=j, value=company)
        _header(ws, top, 2, 2 + len(self.companies))
        for i, year in enumerate(self.years, top + 1):
            ws.cell(row=i, column=2, value=year).border = BORDER
            for j in range(3, 3 + len(self.companies)):
                cell = ws.cell(row=i, column=j, value=self._lookup(key, f"{get_column_letter(j)}${top}", f"$B{i}"))
                cell.number_format, cell.border = NUMBER_FORMATS[unit], BORDER

    def _line_chart(self, ws, top, title, num_format):
        chart = LineChart()
        chart.title, chart.y_axis.numFmt, chart.x_axis.title = title, num_format, "Financial year"
        chart.height, chart.width = 7.5, 14
        chart.add_data(Reference(ws, min_col=3, max_col=2 + len(self.companies), min_row=top,
                                 max_row=top + len(self.years)), titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=2, min_row=top + 1, max_row=top + len(self.years)))
        for series in chart.series:
            series.smooth = False
        return chart

    def _validation_sheet(self):
        ws = self.wb.create_sheet("Data Quality")
        ws["A1"] = "Issues found in the raw data"
        ws["A1"].font = Font(name=FONT, bold=True, size=12, color=INK)
        row = 2
        for table, title in ((self.issues, None), (self.fixes, "Fixes applied")):
            if title:
                row += 1
                ws.cell(row=row, column=1, value=title).font = Font(name=FONT, bold=True, size=12, color=INK)
                row += 1
            if table.empty:
                ws.cell(row=row, column=1, value="None")
                row += 2
                continue
            for j, h in enumerate(table.columns, 1):
                ws.cell(row=row, column=j, value=h)
            _header(ws, row, 1, len(table.columns))
            for rec in table.itertuples(index=False):
                row += 1
                for j, v in enumerate(rec, 1):
                    ws.cell(row=row, column=j, value=v).border = BORDER
            row += 2
        for col, width in zip("ABCDE", [24, 30, 10, 24, 70], strict=True):
            ws.column_dimensions[col].width = width

    def _macro_sheet(self):
        if not self.macro_tables:
            return
        ws = self.wb.create_sheet("Macro")
        ws["A1"] = "Macro sensitivity (simulated macro path; values computed by PeerLens)"
        ws["A1"].font = Font(name=FONT, bold=True, size=12, color=INK)
        row = 3
        for title, table in self.macro_tables.items():
            ws.cell(row=row, column=1, value=title).font = Font(name=FONT, bold=True, color=INK)
            row += 1
            for j, h in enumerate(table.columns, 1):
                ws.cell(row=row, column=j, value=str(h))
            _header(ws, row, 1, len(table.columns))
            for rec in table.itertuples(index=False):
                row += 1
                for j, v in enumerate(rec, 1):
                    v = None if (isinstance(v, float) and pd.isna(v)) else v
                    cell = ws.cell(row=row, column=j, value=v)
                    cell.border = BORDER
                    if isinstance(v, float):
                        cell.number_format = "0.000"
            row += 3
        for j in range(1, 9):
            ws.column_dimensions[get_column_letter(j)].width = 22 if j == 1 else 16

    def _notes_sheet(self):
        ws = self.wb.create_sheet("Notes")
        notes = [
            ("Purpose", "Peer benchmarking inside one Nifty 500 industry for a credit or equity analyst."),
            ("Data source", self.source_label),
            ("Units", "₹ crore. Financial years end in March (FY2025 = April 2024 to March 2025)."),
            ("Thresholds", "Cross-industry rules of thumb; edit them on the Thresholds sheet."),
            ("n/a values", "A ratio is n/a when a line item is not reported or its denominator is zero "
                           "(e.g. interest coverage for a debt-free company)."),
            ("Limitations", "ROE and ROCE use closing balances, not averages. Bank balance sheets have no "
                            "current assets or liabilities, so liquidity ratios do not apply to them."),
            ("Colour code", "Blue text = input values, black = formulas, yellow = editable cells."),
        ]
        ws["A1"], ws["B1"] = "Item", "Note"
        _header(ws, 1, 1, 2)
        for i, (item, note) in enumerate(notes, 2):
            ws.cell(row=i, column=1, value=item).font = Font(name=FONT, bold=True)
            ws.cell(row=i, column=2, value=note).alignment = Alignment(wrap_text=True)
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 110
