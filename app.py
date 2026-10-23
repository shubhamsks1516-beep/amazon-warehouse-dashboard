import os
import shutil
import re
from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import csv
import io

from data_engine import WarehouseDataEngine
from exporters import generate_excel_export, generate_pdf_export

app = FastAPI(title="Amazon Logistic Warehouse High-Selling Dashboard", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistent data engine instance
# Vercel serverless has a read-only filesystem except /tmp
IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
UPLOAD_DIR = "/tmp/uploads" if IS_VERCEL else os.path.join(os.path.dirname(__file__), "uploads")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

engine = WarehouseDataEngine()
# Clean Zero-State: No automatic preloading. The dashboard starts strictly at 0.
# Data is ingested and analyzed ONLY when the user uploads their raw data file.

# Mount static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    candidates = [
        os.path.join(STATIC_DIR, "index.html"),
        os.path.join(os.path.dirname(__file__), "index.html"),
        os.path.join(os.path.dirname(__file__), "public", "index.html"),
        os.path.join(os.getcwd(), "static", "index.html"),
        os.path.join(os.getcwd(), "public", "index.html"),
        os.path.join(os.getcwd(), "index.html"),
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Amazon Warehouse Dashboard</h1><p>Frontend static files loading...</p>")


@app.post("/api/clear")
@app.post("/clear")
async def clear_data():
    """
    Clears all loaded data and resets dashboard back to clean zero state.
    """
    engine.clear()
    return {"status": "success", "message": "Dashboard reset to clean zero state"}


@app.get("/api/status")
@app.get("/status")
async def get_system_status():
    return {
        "has_data": engine.has_data,
        "dataset_name": engine.dataset_name,
        "total_rows": engine.total_rows,
        "min_date": engine.min_date,
        "max_date": engine.max_date,
        "mapped_columns": engine.active_columns
    }


@app.post("/api/upload")
@app.post("/upload")
async def upload_raw_data(file: UploadFile = File(...)):
    """
    Accepts CSV, TSV, or XLSX files of any size (up to millions of rows).
    """
    try:
        raw_name = os.path.basename(file.filename or "uploaded_data.csv")
        safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', raw_name)
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in ['.csv', '.xlsx', '.xls', '.tsv', '.txt', '.parquet']:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a CSV, XLSX, TSV, or TXT file.")

        dest_path = os.path.join(UPLOAD_DIR, safe_name)

        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        result = engine.ingest_file(dest_path)
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File processing error: {str(e)}")


@app.get("/api/summary")
@app.get("/summary")
async def get_summary(
    time_frame: str = Query("all_time", pattern="^(all_time|month_1|days_7|d_minus_1|custom)$"),
    status_filter: str = Query("delivered_only", pattern="^(all|delivered_only)$"),
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None
):
    summary = engine.get_summary_metrics(
        time_frame=time_frame,
        status_filter=status_filter,
        custom_start=custom_start,
        custom_end=custom_end
    )
    return summary


@app.get("/api/top-selling")
@app.get("/top-selling")
async def get_top_selling(
    time_frame: str = Query("all_time", pattern="^(all_time|month_1|days_7|d_minus_1|custom)$"),
    sort_by: str = Query("units", pattern="^(units|revenue)$"),
    limit: int = Query(50, ge=5, le=1000),
    search: Optional[str] = None,
    category: Optional[str] = None,
    status_filter: str = Query("delivered_only", pattern="^(all|delivered_only)$"),
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None
):
    items = engine.get_top_selling_products(
        time_frame=time_frame,
        limit=limit,
        sort_by=sort_by,
        search_query=search,
        category_filter=category,
        custom_start=custom_start,
        custom_end=custom_end,
        status_filter=status_filter
    )
    return {"count": len(items), "items": items}


@app.get("/api/sales-trend")
@app.get("/sales-trend")
async def get_sales_trend(
    time_frame: str = Query("all_time", pattern="^(all_time|month_1|days_7|d_minus_1|custom)$"),
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None
):
    trend = engine.get_sales_trend(
        time_frame=time_frame,
        custom_start=custom_start,
        custom_end=custom_end
    )
    return trend


@app.get("/api/categories")
@app.get("/categories")
async def get_categories(
    time_frame: str = Query("all_time", pattern="^(all_time|month_1|days_7|d_minus_1|custom)$"),
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None
):
    categories = engine.get_category_distribution(
        time_frame=time_frame,
        custom_start=custom_start,
        custom_end=custom_end
    )
    all_cats = engine.get_all_categories()
    return {"top_categories": categories, "all_categories": all_cats}


@app.get("/api/hourly-heatmap")
@app.get("/hourly-heatmap")
async def get_hourly_heatmap(time_frame: str = Query("all_time")):
    return engine.get_hourly_heatmap(time_frame=time_frame)


@app.get("/api/top-chart")
@app.get("/top-chart")
async def get_top_chart(
    time_frame: str = Query("all_time", pattern="^(all_time|month_1|days_7|d_minus_1|custom)$"),
    metric: str = Query("units", pattern="^(units|revenue)$"),
    limit: int = Query(10, ge=3, le=25),
    status_filter: str = Query("delivered_only", pattern="^(all|delivered_only)$"),
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None
):
    return engine.get_top_chart_items(
        time_frame=time_frame,
        metric=metric,
        limit=limit,
        status_filter=status_filter,
        custom_start=custom_start,
        custom_end=custom_end
    )


@app.get("/api/export-csv")
@app.get("/export-csv")
async def export_csv(
    time_frame: str = Query("all_time"),
    sort_by: str = Query("units"),
    status_filter: str = Query("delivered_only"),
    search: Optional[str] = None,
    category: Optional[str] = None,
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None
):
    items = engine.get_top_selling_products(
        time_frame=time_frame,
        limit=5000,
        sort_by=sort_by,
        search_query=search,
        category_filter=category,
        custom_start=custom_start,
        custom_end=custom_end,
        status_filter=status_filter
    )

    summary = engine.get_summary_metrics(
        time_frame=time_frame,
        status_filter=status_filter,
        custom_start=custom_start,
        custom_end=custom_end
    )
    has_revenue = summary.get("has_revenue", True)

    output = io.StringIO()
    writer = csv.writer(output)

    if has_revenue:
        writer.writerow([
            "Rank", "ASIN", "SKU", "Product Title", "Category", 
            "Units Sold", "Units Share %", "Total Revenue (INR)", "Revenue Share %", "Average Price", 
            "Total Orders", "Active Days", "Units/Day Velocity", "Velocity Tag"
        ])
        for it in items:
            writer.writerow([
                it["rank"], it["asin"], it["sku"], it["title"], it["category"],
                it["units_sold"], f"{it.get('units_share', 0.0)}%",
                it["revenue"], f"{it.get('revenue_share', 0.0)}%", it["avg_price"],
                it["order_count"], it["active_days"], it["velocity_daily"],
                it["velocity_badge"]
            ])
    else:
        writer.writerow([
            "Rank", "ASIN", "SKU", "Product Title", "Category", 
            "Units Picked", "Volume Share %", "Customer Orders", "Order Share %", "Units Per Order", 
            "Active Days", "Units/Day Velocity", "Velocity Tag"
        ])
        for it in items:
            writer.writerow([
                it["rank"], it["asin"], it["sku"], it["title"], it["category"],
                it["units_sold"], f"{it.get('units_share', 0.0)}%",
                it["order_count"], f"{it.get('order_share', 0.0)}%", it.get("units_per_order", 1.0),
                it["active_days"], it["velocity_daily"],
                it["velocity_badge"]
            ])

    output.seek(0)
    filename = f"Amazon_Warehouse_Top_Selling_{time_frame}.csv"
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/api/export-excel")
@app.get("/export-excel")
async def export_excel(
    time_frame: str = Query("all_time"),
    sort_by: str = Query("units"),
    status_filter: str = Query("delivered_only"),
    search: Optional[str] = None,
    category: Optional[str] = None,
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None
):
    items = engine.get_top_selling_products(
        time_frame=time_frame,
        limit=5000,
        sort_by=sort_by,
        search_query=search,
        category_filter=category,
        custom_start=custom_start,
        custom_end=custom_end,
        status_filter=status_filter
    )
    summary = engine.get_summary_metrics(
        time_frame=time_frame,
        status_filter=status_filter,
        custom_start=custom_start,
        custom_end=custom_end
    )

    excel_buffer = generate_excel_export(items, summary, time_frame)
    filename = f"Amazon_Warehouse_Top_Selling_{time_frame}.xlsx"
    return Response(
        content=excel_buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/api/export-pdf")
@app.get("/export-pdf")
async def export_pdf(
    time_frame: str = Query("all_time"),
    sort_by: str = Query("units"),
    status_filter: str = Query("delivered_only"),
    search: Optional[str] = None,
    category: Optional[str] = None,
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None
):
    items = engine.get_top_selling_products(
        time_frame=time_frame,
        limit=100,
        sort_by=sort_by,
        search_query=search,
        category_filter=category,
        custom_start=custom_start,
        custom_end=custom_end,
        status_filter=status_filter
    )
    summary = engine.get_summary_metrics(
        time_frame=time_frame,
        status_filter=status_filter,
        custom_start=custom_start,
        custom_end=custom_end
    )

    pdf_buffer = generate_pdf_export(items, summary, time_frame)
    filename = f"Amazon_Warehouse_Top_Selling_{time_frame}.pdf"
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
