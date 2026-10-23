import os
import io
from typing import List, Dict, Any
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def format_inr_excel(val: float) -> str:
    return f"₹ {val:,.2f}"

def generate_excel_export(items: List[Dict[str, Any]], summary: Dict[str, Any], time_frame_label: str) -> io.BytesIO:
    """
    Generates an executive-formatted Excel spreadsheet with headers,
    currency styling, percentages, and total row.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "High Selling Products"
    ws.views.sheetView[0].showGridLines = True

    # Color definitions (Amazon Warehouse Slate & Gold theme)
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    sub_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    gold_fill = PatternFill(start_color="F59E0B", end_color="F59E0B", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    total_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

    font_title = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
    font_sub = Font(name="Calibri", size=11, italic=True, color="E2E8F0")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_data = Font(name="Calibri", size=10)
    font_bold = Font(name="Calibri", size=10, bold=True)
    font_gold = Font(name="Calibri", size=10, bold=True, color="B45309")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # 1. Main Title Header (Row 1-2)
    ws.merge_cells("A1:L1")
    title_cell = ws["A1"]
    title_cell.value = "AMAZON LOGISTICS WAREHOUSE - HIGH-SELLING PERFORMANCE REPORT"
    title_cell.font = font_title
    title_cell.fill = header_fill
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    # Subtitle with metadata (Row 2)
    ws.merge_cells("A2:L2")
    sub_cell = ws["A2"]
    total_units_str = f"{summary.get('total_units', 0):,}"
    has_revenue = summary.get('has_revenue', True)
    
    if has_revenue:
        total_rev_str = f"₹ {summary.get('total_revenue', 0.0):,.2f}"
        sub_cell.value = f"Time Horizon: {time_frame_label.upper()}  |  Total Units Sold: {total_units_str}  |  Total GMV: {total_rev_str}  |  Total Orders: {summary.get('total_orders', 0):,}"
        headers = [
            "Rank", "ASIN", "SKU", "Product Title", "Category", 
            "Units Sold", "Units Share %", "Total Revenue (₹)", "Revenue Share %", 
            "Avg Price (₹)", "Orders Count", "Daily Velocity"
        ]
    else:
        basket_str = f"{summary.get('avg_units_per_order', 1.0)} Units/Order"
        sub_cell.value = f"Time Horizon: {time_frame_label.upper()}  |  Total Dispatched Units: {total_units_str}  |  Total Customer Orders: {summary.get('total_orders', 0):,}  |  Basket Density: {basket_str} (Amazon WMS Outbound Audit Mode)"
        headers = [
            "Rank", "ASIN", "SKU", "Product Title", "Category", 
            "Units Picked", "Volume Share %", "Customer Orders", "Order Share %", 
            "Units / Order", "Active Days", "Daily Velocity"
        ]

    sub_cell.font = font_sub
    sub_cell.fill = sub_fill
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 24

    ws.row_dimensions[3].height = 10 # Empty spacer row

    # 2. Table Column Headers (Row 4)
    ws.row_dimensions[4].height = 26
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center" if col_idx in [1, 2, 3, 5, 12] else "right" if col_idx in [6, 7, 8, 9, 10, 11] else "left", vertical="center")
        cell.border = thin_border

    # 3. Populate Rows
    current_row = 5
    for item in items:
        ws.row_dimensions[current_row].height = 20
        is_zebra = (current_row % 2 == 0)
        row_fill = zebra_fill if is_zebra else None

        if has_revenue:
            values = [
                item["rank"],
                item["asin"],
                item["sku"],
                item["title"],
                item["category"],
                item["units_sold"],
                f"{item.get('units_share', 0.0):.2f}%",
                item["revenue"],
                f"{item.get('revenue_share', 0.0):.2f}%",
                item["avg_price"],
                item["order_count"],
                f"{item['velocity_daily']}/day"
            ]
        else:
            values = [
                item["rank"],
                item["asin"],
                item["sku"],
                item["title"],
                item["category"],
                item["units_sold"],
                f"{item.get('units_share', 0.0):.2f}%",
                item["order_count"],
                f"{item.get('order_share', 0.0):.2f}%",
                item.get("units_per_order", 1.0),
                item["active_days"],
                f"{item['velocity_daily']}/day"
            ]

        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = font_bold if col_idx in [1, 6, 8] else font_data
            if row_fill:
                cell.fill = row_fill
            cell.border = thin_border
            
            # Alignments & Numbers
            if col_idx == 1:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [2, 3, 5, 12]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [6, 11]:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx == 8:
                if has_revenue:
                    cell.number_format = '"₹" #,##0.00'
                else:
                    cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx == 10:
                if has_revenue:
                    cell.number_format = '"₹" #,##0.00'
                else:
                    cell.number_format = "0.00"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in [7, 9]:
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

        current_row += 1

    # 4. Total Summary Row
    ws.row_dimensions[current_row].height = 24
    total_label = ws.cell(row=current_row, column=4, value="TOTAL SUMMARY (FILTERED VIEW)" if has_revenue else "TOTAL OUTBOUND DISPATCHES")
    total_label.font = font_bold
    total_label.alignment = Alignment(horizontal="right", vertical="center")
    
    total_units_cell = ws.cell(row=current_row, column=6, value=sum(it["units_sold"] for it in items))
    total_units_cell.font = font_bold
    total_units_cell.number_format = "#,##0"
    total_units_cell.alignment = Alignment(horizontal="right", vertical="center")

    total_col8_val = sum(it["revenue"] for it in items) if has_revenue else sum(it["order_count"] for it in items)
    total_col8_cell = ws.cell(row=current_row, column=8, value=total_col8_val)
    total_col8_cell.font = font_bold
    total_col8_cell.number_format = '"₹" #,##0.00' if has_revenue else "#,##0"
    total_col8_cell.alignment = Alignment(horizontal="right", vertical="center")

    for col in range(1, len(headers) + 1):
        c = ws.cell(row=current_row, column=col)
        c.fill = total_fill
        c.border = thin_border

    # Auto-adjust column widths
    column_widths = {
        1: 8,   # Rank
        2: 14,  # ASIN
        3: 14,  # SKU
        4: 45,  # Product Title
        5: 22,  # Category
        6: 14,  # Units Sold
        7: 14,  # Units Share %
        8: 18,  # Total Revenue ₹
        9: 16,  # Revenue Share %
        10: 14, # Avg Price ₹
        11: 14, # Orders Count
        12: 15  # Velocity
    }
    for col_idx, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_pdf_export(items: List[Dict[str, Any]], summary: Dict[str, Any], time_frame_label: str) -> io.BytesIO:
    """
    Generates a high-resolution, landscape-oriented executive PDF report
    with KPIs and top selling product leaderboard.
    """
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(letter),
        leftMargin=30,
        rightMargin=30,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0F172A'),
        fontName='Helvetica-Bold',
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#475569'),
        spaceAfter=12
    )
    th_style = ParagraphStyle(
        'TableHeader',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1 # Center
    )
    td_style = ParagraphStyle(
        'TableCell',
        fontName='Helvetica',
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#1E293B')
    )
    td_bold = ParagraphStyle(
        'TableCellBold',
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#0F172A')
    )

    elements = []

    # Title & Subtitle
    elements.append(Paragraph("AMAZON LOGISTICS WAREHOUSE - HIGH-SELLING PERFORMANCE REPORT", title_style))
    has_revenue = summary.get('has_revenue', True)
    
    if has_revenue:
        sub_text = (
            f"<b>Time Horizon:</b> {time_frame_label.upper()} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Total Units Dispatched:</b> {summary.get('total_units', 0):,} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Total Gross Revenue:</b> ₹ {summary.get('total_revenue', 0.0):,.2f} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Total Orders:</b> {summary.get('total_orders', 0):,} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>AOV:</b> ₹ {summary.get('aov', 0.0):,.2f}"
        )
        col_widths = [26, 65, 60, 200, 95, 45, 45, 65, 45, 45, 45]
        table_data = [[
            Paragraph("<b>Rank</b>", th_style),
            Paragraph("<b>ASIN</b>", th_style),
            Paragraph("<b>SKU</b>", th_style),
            Paragraph("<b>Product Title</b>", th_style),
            Paragraph("<b>Category</b>", th_style),
            Paragraph("<b>Units</b>", th_style),
            Paragraph("<b>Unit %</b>", th_style),
            Paragraph("<b>Revenue (₹)</b>", th_style),
            Paragraph("<b>Rev %</b>", th_style),
            Paragraph("<b>Avg ₹</b>", th_style),
            Paragraph("<b>Run-Rate</b>", th_style)
        ]]
    else:
        basket_str = f"{summary.get('avg_units_per_order', 1.0)} units/order"
        sub_text = (
            f"<b>Time Horizon:</b> {time_frame_label.upper()} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Total Dispatched Units:</b> {summary.get('total_units', 0):,} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Customer Orders:</b> {summary.get('total_orders', 0):,} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Basket Density:</b> {basket_str} (Amazon WMS Outbound Audit Mode)"
        )
        col_widths = [26, 65, 60, 200, 95, 45, 45, 65, 45, 45, 45]
        table_data = [[
            Paragraph("<b>Rank</b>", th_style),
            Paragraph("<b>ASIN</b>", th_style),
            Paragraph("<b>SKU</b>", th_style),
            Paragraph("<b>Product Title</b>", th_style),
            Paragraph("<b>Category</b>", th_style),
            Paragraph("<b>Units</b>", th_style),
            Paragraph("<b>Vol %</b>", th_style),
            Paragraph("<b>Orders</b>", th_style),
            Paragraph("<b>Order %</b>", th_style),
            Paragraph("<b>Units/Ord</b>", th_style),
            Paragraph("<b>Run-Rate</b>", th_style)
        ]]

    elements.append(Paragraph(sub_text, subtitle_style))
    elements.append(Spacer(1, 8))

    # Limit to top 40 for clean PDF layout
    display_items = items[:40]
    for it in display_items:
        title_truncated = it["title"][:48] + "..." if len(it["title"]) > 50 else it["title"]
        if has_revenue:
            table_data.append([
                Paragraph(f"#{it['rank']}", td_bold),
                Paragraph(it["asin"], td_style),
                Paragraph(it["sku"], td_style),
                Paragraph(title_truncated, td_style),
                Paragraph(it["category"][:18], td_style),
                Paragraph(f"{it['units_sold']:,}", td_bold),
                Paragraph(f"{it.get('units_share', 0.0):.1f}%", td_style),
                Paragraph(f"₹{it['revenue']:,.0f}", td_bold),
                Paragraph(f"{it.get('revenue_share', 0.0):.1f}%", td_style),
                Paragraph(f"₹{it['avg_price']:.0f}", td_style),
                Paragraph(f"{it['velocity_daily']}/d", td_style)
            ])
        else:
            table_data.append([
                Paragraph(f"#{it['rank']}", td_bold),
                Paragraph(it["asin"], td_style),
                Paragraph(it["sku"], td_style),
                Paragraph(title_truncated, td_style),
                Paragraph(it["category"][:18], td_style),
                Paragraph(f"{it['units_sold']:,}", td_bold),
                Paragraph(f"{it.get('units_share', 0.0):.1f}%", td_style),
                Paragraph(f"{it['order_count']:,}", td_bold),
                Paragraph(f"{it.get('order_share', 0.0):.1f}%", td_style),
                Paragraph(f"{it.get('units_per_order', 1.0)}", td_style),
                Paragraph(f"{it['velocity_daily']}/d", td_style)
            ])

    pdf_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    pdf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')])
    ]))

    elements.append(pdf_table)
    doc.build(elements)
    output.seek(0)
    return output
