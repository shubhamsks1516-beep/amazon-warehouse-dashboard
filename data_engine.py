import os
import duckdb
import polars as pl
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import re

class WarehouseDataEngine:
    """
    High-performance in-memory columnar data engine powered by DuckDB and Polars.
    Engineered to parse millions of raw order rows in 1-2 seconds with zero UI lag.
    """
    def __init__(self, db_path: str = ":memory:"):
        self.con = duckdb.connect(db_path)
        self.has_data = False
        self.total_rows = 0
        self.min_date: Optional[str] = None
        self.max_date: Optional[str] = None
        self.active_columns: Dict[str, str] = {}
        self.dataset_name = "None"
        
        # Init tables
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id VARCHAR,
                order_date TIMESTAMP,
                date_str VARCHAR,
                asin VARCHAR,
                sku VARCHAR,
                product_name VARCHAR,
                category VARCHAR,
                quantity INTEGER,
                item_price DOUBLE,
                total_amount DOUBLE,
                order_status VARCHAR,
                fulfillment_channel VARCHAR,
                city VARCHAR
            );
        """)

    def clear(self):
        """
        Resets engine back to initial clean zero-state (no raw data).
        """
        self.con.execute("TRUNCATE TABLE orders;")
        self.has_data = False
        self.total_rows = 0
        self.min_date = None
        self.max_date = None
        self.active_columns = {}
        self.dataset_name = "None"

    def _normalize_header(self, col: str) -> str:
        return re.sub(r'[^a-z0-9]', '', str(col).lower())

    def detect_and_map_columns(self, columns: List[str]) -> Dict[str, str]:
        """
        Smart column auto-detection for Amazon Seller Central, Vendor Central,
        FBA Fulfillment, Easy Ship, and WMS raw reports.
        """
        mapping = {
            'order_id': None,
            'order_date': None,
            'asin': None,
            'sku': None,
            'product_name': None,
            'category': None,
            'quantity': None,
            'item_price': None,
            'order_status': None,
            'fulfillment_channel': None,
            'city': None
        }

        patterns = {
            'order_id': ['orderid', 'amazonorderid', 'order_id', 'orderno', 'ordernumber', 'order', 'referenceidvalue', 'referenceid', 'customerorderid'],
            'order_date': ['purchasedate', 'orderdate', 'date', 'createdat', 'ordertime', 'timestamp', 'invoicedate', 'datetime'],
            'asin': ['asin', 'productid', 'itemcode', 'asin1', 'itemid'],
            'sku': ['sellersku', 'sku', 'skuid', 'msku', 'productsku', 'partnumber', 'fnsku'],
            'product_name': ['productname', 'title', 'itemname', 'itemdescription', 'description', 'producttitle', 'name'],
            'category': ['category', 'productgroup', 'subcategory', 'department', 'glproductgrouptype'],
            'quantity': ['quantity', 'qty', 'itemquantity', 'unitsordered', 'quantitypurchased', 'units', 'count'],
            'item_price': ['itemprice', 'price', 'itemrevenue', 'itemtotal', 'orderamount', 'amount', 'itemamount', 'salesprice', 'subtotal'],
            'order_status': ['orderstatus', 'status', 'deliverystatus', 'shipmentstatus', 'state', 'process'],
            'fulfillment_channel': ['fulfillmentchannel', 'channel', 'fulfillment', 'shipmenttype', 'shipmethod'],
            'city': ['city', 'shipcity', 'destinationcity', 'region', 'state']
        }

        col_norm = {col: self._normalize_header(col) for col in columns}

        for target_key, search_terms in patterns.items():
            # Exact match check first
            for original_col, norm in col_norm.items():
                if norm in search_terms:
                    mapping[target_key] = original_col
                    break
            
            # Partial match if not found
            if not mapping[target_key]:
                for original_col, norm in col_norm.items():
                    for term in search_terms:
                        if term in norm:
                            mapping[target_key] = original_col
                            break
                    if mapping[target_key]:
                        break

        return mapping

    def ingest_file(self, file_path: str, custom_mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Ingests CSV, TSV, or Excel files into DuckDB using Polars reader for extreme speed.
        """
        ext = os.path.splitext(file_path)[1].lower()
        
        # Fast read using Polars
        if ext in ['.csv', '.txt', '.tsv']:
            # Auto-detect delimiter
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
                sep = '\t' if '\t' in first_line else ','

            df = pl.read_csv(file_path, separator=sep, ignore_errors=True, infer_schema_length=10000, truncate_ragged_lines=True)
        elif ext in ['.xlsx', '.xls']:
            df = pl.read_excel(file_path)
        elif ext == '.parquet':
            df = pl.read_parquet(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

        cols = df.columns
        mapping = custom_mapping or self.detect_and_map_columns(cols)
        self.active_columns = mapping

        # Ensure required identifiers exist
        has_id = mapping.get('order_id')
        has_asin = mapping.get('asin') or mapping.get('sku') or mapping.get('product_name')
        if not has_asin:
            # Fallback to first text column
            for col in cols:
                if df[col].dtype == pl.Utf8:
                    mapping['product_name'] = col
                    break

        # Register dataframe with DuckDB natively without pyarrow
        self.con.register('raw_upload_df', df)

        # Build dynamic SQL ingestion expression
        def col_expr(key, default_val, cast_type):
            orig = mapping.get(key)
            if orig and orig in cols:
                # Handle escaping column names
                safe_col = f'"{orig}"'
                if cast_type == 'TIMESTAMP':
                    return (
                        f"COALESCE("
                        f"TRY_CAST({safe_col} AS TIMESTAMP), "
                        f"TRY_CAST(REPLACE(SUBSTRING(CAST({safe_col} AS VARCHAR), 1, 19), 'T', ' ') AS TIMESTAMP), "
                        f"TRY_CAST(STRPTIME(CAST({safe_col} AS VARCHAR), '%d/%m/%Y %H:%M:%S') AS TIMESTAMP), "
                        f"TRY_CAST(STRPTIME(CAST({safe_col} AS VARCHAR), '%d-%m-%Y %H:%M:%S') AS TIMESTAMP), "
                        f"TRY_CAST(STRPTIME(CAST({safe_col} AS VARCHAR), '%m/%d/%Y %H:%M:%S') AS TIMESTAMP), "
                        f"TRY_CAST(STRPTIME(CAST({safe_col} AS VARCHAR), '%d/%m/%Y') AS TIMESTAMP), "
                        f"TRY_CAST(STRPTIME(CAST({safe_col} AS VARCHAR), '%d-%m-%Y') AS TIMESTAMP), "
                        f"TRY_CAST(STRPTIME(CAST({safe_col} AS VARCHAR), '%Y-%m-%d') AS TIMESTAMP), "
                        f"CURRENT_TIMESTAMP)"
                    )
                elif cast_type == 'INTEGER':
                    return f"CAST(ROUND(ABS(COALESCE(TRY_CAST(REPLACE(CAST({safe_col} AS VARCHAR), ',', '') AS DOUBLE), 1.0))) AS INTEGER)"
                elif cast_type == 'DOUBLE':
                    return f"COALESCE(ABS(TRY_CAST(REPLACE(REPLACE(REPLACE(CAST({safe_col} AS VARCHAR), '₹', ''), 'INR', ''), ',', '') AS DOUBLE)), 0.0)"
                else:
                    return f"COALESCE(CAST({safe_col} AS VARCHAR), {default_val})"
            return default_val

        order_id_sql = col_expr('order_id', "CAST(row_number() OVER () AS VARCHAR)", 'VARCHAR')
        order_date_sql = col_expr('order_date', "CURRENT_TIMESTAMP", 'TIMESTAMP')
        asin_sql = col_expr('asin', "'N/A'", 'VARCHAR')
        sku_sql = col_expr('sku', "'N/A'", 'VARCHAR')
        product_name_sql = col_expr('product_name', "'Unknown Item'", 'VARCHAR')
        
        category_orig = mapping.get('category')
        if category_orig and category_orig in cols:
            category_sql = f'COALESCE(CAST("{category_orig}" AS VARCHAR), \'General\')'
        else:
            category_sql = f"""
                CASE 
                    WHEN REGEXP_MATCHES(LOWER({product_name_sql}), 'milk|ghee|butter|dahi|chach|paneer|curd|cheese') THEN 'Dairy & Fresh'
                    WHEN REGEXP_MATCHES(LOWER({product_name_sql}), 'potato|onion|tomato|apple|banana|vegetable|fresh|fruit|lemon|ginger|garlic') THEN 'Fruits & Vegetables'
                    WHEN REGEXP_MATCHES(LOWER({product_name_sql}), 'atta|rice|dal|oil|salt|sugar|masala|suji|maida|poha|besan|flour|grain|spice') THEN 'Grocery & Staples'
                    WHEN REGEXP_MATCHES(LOWER({product_name_sql}), 'biscuit|chips|chocolate|snack|namkeen|maggi|noodle|pasta|cookies|tedhe medhe|kurkure|bhujia|bar') THEN 'Snacks & Munchies'
                    WHEN REGEXP_MATCHES(LOWER({product_name_sql}), 'tea|coffee|drink|juice|coke|pepsi|water|soda|beverage') THEN 'Beverages'
                    WHEN REGEXP_MATCHES(LOWER({product_name_sql}), 'shampoo|soap|sunscreen|serum|cream|diaper|facewash|lotion|nail|perfume|deo|toothpaste|brush|skin|wash') THEN 'Personal Care'
                    WHEN REGEXP_MATCHES(LOWER({product_name_sql}), 'detergent|harpic|surf|lizol|cleaner|freshener|vim|bag|toilet|cleaning') THEN 'Home & Cleaning'
                    WHEN REGEXP_MATCHES(LOWER({product_name_sql}), 'cable|charger|powerbank|battery|earphone|phone|bulb|adapter|usb|toy|electronics') THEN 'Electronics & Toys'
                    ELSE 'General FMCG'
                END
            """

        quantity_sql = col_expr('quantity', "1", 'INTEGER')
        item_price_sql = col_expr('item_price', "0.0", 'DOUBLE')
        status_sql = col_expr('order_status', "'Shipped'", 'VARCHAR')
        channel_sql = col_expr('fulfillment_channel', "'Amazon Logistics'", 'VARCHAR')
        city_sql = col_expr('city', "'Local'", 'VARCHAR')

        # Drop and populate master orders table
        self.con.execute("TRUNCATE TABLE orders;")
        insert_sql = f"""
            INSERT INTO orders
            SELECT 
                {order_id_sql} AS order_id,
                COALESCE({order_date_sql}, CURRENT_TIMESTAMP) AS order_date,
                STRFTIME(COALESCE({order_date_sql}, CURRENT_TIMESTAMP), '%Y-%m-%d') AS date_str,
                {asin_sql} AS asin,
                {sku_sql} AS sku,
                {product_name_sql} AS product_name,
                {category_sql} AS category,
                {quantity_sql} AS quantity,
                {item_price_sql} AS item_price,
                ({quantity_sql} * {item_price_sql}) AS total_amount,
                {status_sql} AS order_status,
                {channel_sql} AS fulfillment_channel,
                {city_sql} AS city
            FROM raw_upload_df;
        """
        self.con.execute(insert_sql)
        self.con.unregister('raw_upload_df')

        # Stats query
        stats = self.con.execute("""
            SELECT 
                COUNT(*) as total_rows,
                MIN(order_date) as min_date,
                MAX(order_date) as max_date,
                COUNT(DISTINCT asin) as distinct_asins,
                COUNT(DISTINCT sku) as distinct_skus
            FROM orders
        """).fetchone()

        self.total_rows = stats[0]
        self.min_date = str(stats[1]) if stats[1] else None
        self.max_date = str(stats[2]) if stats[2] else None
        self.has_data = True
        self.dataset_name = os.path.basename(file_path)

        return {
            "status": "success",
            "filename": self.dataset_name,
            "total_rows": self.total_rows,
            "min_date": self.min_date,
            "max_date": self.max_date,
            "distinct_asins": stats[3],
            "distinct_skus": stats[4],
            "mapped_columns": mapping
        }

    def _build_date_filter(self, time_frame: str, custom_start: Optional[str] = None, custom_end: Optional[str] = None) -> str:
        """
        Builds high-performance SQL date filter:
        - all_time: Store inception to now
        - month_1: Last 30 Days from max dataset date
        - days_7: Last 7 Days from max dataset date
        - d_minus_1: Exactly yesterday relative to dataset max date
        - custom: start_date to end_date
        """
        if not self.has_data or not self.max_date:
            return "1=1"

        max_dt = self.con.execute("SELECT MAX(order_date) FROM orders").fetchone()[0]
        if not max_dt:
            return "1=1"

        if time_frame == "d_minus_1":
            # Exact yesterday relative to latest transaction in dataset
            yesterday_start = (max_dt - timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
            yesterday_end = (max_dt - timedelta(days=1)).strftime("%Y-%m-%d 23:59:59")
            return f"order_date >= '{yesterday_start}' AND order_date <= '{yesterday_end}'"

        elif time_frame == "days_7":
            start_7d = (max_dt - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
            return f"order_date >= '{start_7d}'"

        elif time_frame == "month_1":
            start_30d = (max_dt - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00")
            return f"order_date >= '{start_30d}'"

        elif time_frame == "custom" and custom_start and custom_end:
            cs = str(custom_start).strip()
            ce = str(custom_end).strip()
            if re.match(r'^\d{4}-\d{2}-\d{2}$', cs) and re.match(r'^\d{4}-\d{2}-\d{2}$', ce):
                return f"order_date >= '{cs} 00:00:00' AND order_date <= '{ce} 23:59:59'"
            return "1=1"

        elif time_frame == "all_time":
            return "1=1"

        return "1=1"

    def get_summary_metrics(self, time_frame: str = "all_time", custom_start: Optional[str] = None, custom_end: Optional[str] = None, status_filter: str = "all") -> Dict[str, Any]:
        """
        Calculates executive KPIs: Revenue, Units, Orders, AOV, Active SKUs.
        """
        if not self.has_data:
            return {"empty": True}

        date_sql = self._build_date_filter(time_frame, custom_start, custom_end)
        status_sql = f"AND LOWER(order_status) NOT IN ('cancelled', 'canceled')" if status_filter == "delivered_only" else ""

        query = f"""
            SELECT 
                COUNT(*) as total_orders,
                COALESCE(SUM(quantity), 0) as total_units,
                COALESCE(SUM(total_amount), 0.0) as total_revenue,
                COALESCE(AVG(total_amount), 0.0) as aov,
                COUNT(DISTINCT asin) as active_asins,
                COUNT(DISTINCT sku) as active_skus,
                MIN(order_date) as start_period,
                MAX(order_date) as end_period
            FROM orders
            WHERE {date_sql} {status_sql};
        """
        row = self.con.execute(query).fetchone()
        
        # Calculate cancellation rate
        cancel_query = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN LOWER(order_status) IN ('cancelled', 'canceled') THEN 1 ELSE 0 END) as cancelled
            FROM orders
            WHERE {date_sql};
        """
        cancel_row = self.con.execute(cancel_query).fetchone()
        cancel_rate = round((cancel_row[1] / cancel_row[0] * 100) if cancel_row and cancel_row[0] > 0 else 0.0, 2)

        start_dt = row[6]
        end_dt = row[7]
        period_days = 1
        if start_dt and end_dt:
            try:
                period_days = max(1, (end_dt.date() - start_dt.date()).days + 1)
            except Exception:
                period_days = 1

        grand_units = int(row[1]) if row[1] else 1
        actual_rev = float(row[2]) if (row[2] is not None) else 0.0
        has_revenue = bool(actual_rev > 0.01)
        grand_rev = actual_rev if has_revenue else 1.0

        # Query Top 5 concentration and #1 Best Seller
        top5_rows = self.con.execute(f"""
            SELECT 
                product_name,
                asin,
                SUM(quantity) as units,
                ROUND(SUM(total_amount), 2) as rev
            FROM orders
            WHERE {date_sql} {status_sql}
            GROUP BY product_name, asin
            ORDER BY units DESC
            LIMIT 5;
        """).fetchall()

        top1_name = "N/A"
        top1_asin = "N/A"
        top1_units = 0
        top1_units_share = 0.0
        top1_rev = 0.0
        top1_rev_share = 0.0
        top5_units_sum = 0
        top5_rev_sum = 0.0

        if top5_rows:
            top1 = top5_rows[0]
            top1_name = str(top1[0])
            top1_asin = str(top1[1])
            top1_units = int(top1[2])
            top1_rev = float(top1[3])
            top1_units_share = round((top1_units / grand_units) * 100, 1)
            top1_rev_share = round((top1_rev / grand_rev) * 100, 1) if has_revenue else 0.0

            top5_units_sum = sum(int(r[2]) for r in top5_rows)
            top5_rev_sum = sum(float(r[3]) for r in top5_rows)

        top5_units_share = round((top5_units_sum / grand_units) * 100, 1)
        top5_rev_share = round((top5_rev_sum / grand_rev) * 100, 1) if has_revenue else 0.0
        avg_units_per_order = round(float(row[1]) / max(1, int(row[0])), 2) if row[0] else 1.0

        return {
            "empty": False,
            "total_orders": int(row[0]),
            "total_units": int(row[1]),
            "total_revenue": round(float(row[2]), 2),
            "aov": round(float(row[3]), 2),
            "active_asins": int(row[4]),
            "active_skus": int(row[5]),
            "start_period": str(row[6]) if row[6] else "",
            "end_period": str(row[7]) if row[7] else "",
            "period_days": period_days,
            "cancel_rate": cancel_rate,
            "time_frame": time_frame,
            "top1_name": top1_name,
            "top1_asin": top1_asin,
            "top1_units": top1_units,
            "top1_units_share": top1_units_share,
            "top1_rev": top1_rev,
            "top1_rev_share": top1_rev_share,
            "top5_units_share": top5_units_share,
            "top5_rev_share": top5_rev_share,
            "has_revenue": has_revenue,
            "avg_units_per_order": avg_units_per_order
        }

    def get_top_selling_products(
        self,
        time_frame: str = "all_time",
        limit: int = 50,
        sort_by: str = "units", # "units" or "revenue"
        search_query: Optional[str] = None,
        category_filter: Optional[str] = None,
        custom_start: Optional[str] = None,
        custom_end: Optional[str] = None,
        status_filter: str = "delivered_only"
    ) -> List[Dict[str, Any]]:
        """
        Returns high-selling items leaderboard ranked by Units or Revenue.
        Includes sales velocity, revenue contribution share, and run-rate metrics.
        """
        if not self.has_data:
            return []

        date_sql = self._build_date_filter(time_frame, custom_start, custom_end)
        status_sql = f"AND LOWER(order_status) NOT IN ('cancelled', 'canceled')" if status_filter == "delivered_only" else ""
        
        search_sql = ""
        if search_query and search_query.strip():
            sq = search_query.strip().lower().replace("'", "''")
            search_sql = f"AND (LOWER(product_name) LIKE '%{sq}%' OR LOWER(asin) LIKE '%{sq}%' OR LOWER(sku) LIKE '%{sq}%')"

        category_sql = ""
        if category_filter and category_filter != "all":
            safe_cat = category_filter.strip().replace("'", "''")
            category_sql = f"AND category = '{safe_cat}'"

        # Calculate Total Store Units & Revenue for exact % contribution
        total_store_row = self.con.execute(f"""
            SELECT 
                COALESCE(SUM(quantity), 1) as grand_units,
                COALESCE(SUM(total_amount), 0.0) as grand_revenue
            FROM orders 
            WHERE {date_sql} {status_sql};
        """).fetchone()

        grand_units = int(total_store_row[0]) if total_store_row and total_store_row[0] > 0 else 1
        actual_grand_revenue = float(total_store_row[1]) if total_store_row and total_store_row[1] is not None else 0.0
        has_revenue = bool(actual_grand_revenue > 0.01)
        grand_revenue = actual_grand_revenue if has_revenue else 1.0

        total_orders_row = self.con.execute(f"SELECT COUNT(DISTINCT order_id) FROM orders WHERE {date_sql} {status_sql};").fetchone()
        grand_orders = int(total_orders_row[0]) if total_orders_row and total_orders_row[0] > 0 else 1

        if has_revenue:
            order_by_col = "total_units DESC" if sort_by == "units" else "total_revenue DESC"
        else:
            order_by_col = "total_units DESC" if sort_by == "units" else "order_count DESC"

        query = f"""
            SELECT 
                asin,
                sku,
                product_name,
                category,
                SUM(quantity) as total_units,
                ROUND(SUM(total_amount), 2) as total_revenue,
                ROUND(AVG(item_price), 2) as avg_price,
                COUNT(DISTINCT order_id) as order_count,
                COUNT(DISTINCT date_str) as active_days
            FROM orders
            WHERE {date_sql} {status_sql} {search_sql} {category_sql}
            GROUP BY asin, sku, product_name, category
            ORDER BY {order_by_col}
            LIMIT {limit};
        """
        rows = self.con.execute(query).fetchall()

        # Calculate Period Duration
        period_days_row = self.con.execute(f"SELECT MIN(order_date), MAX(order_date) FROM orders WHERE {date_sql} {status_sql};").fetchone()
        period_days = 1
        if period_days_row and period_days_row[0] and period_days_row[1]:
            try:
                period_days = max(1, (period_days_row[1].date() - period_days_row[0].date()).days + 1)
            except Exception:
                period_days = 1

        results = []
        cumulative_share_counter = 0.0
        for idx, r in enumerate(rows, 1):
            units = int(r[4])
            rev = float(r[5])
            active_days = max(1, int(r[8]))
            velocity_per_day = round(units / period_days, 1)
            consistency_pct = round(min(100.0, (active_days / period_days) * 100), 1)
            units_share = round((units / grand_units) * 100, 2)
            revenue_share = round((rev / grand_revenue) * 100, 2) if has_revenue else 0.0
            
            # Pareto accumulates units when revenue is absent or when sorted by units
            share_to_accumulate = units_share if (not has_revenue or sort_by == "units") else revenue_share
            cumulative_share_counter += share_to_accumulate

            # Determine product velocity tag
            if velocity_per_day >= 30:
                velocity_badge = "🔥 Super Fast Mover"
                badge_color = "amber"
            elif velocity_per_day >= 10:
                velocity_badge = "⚡ Fast Mover"
                badge_color = "emerald"
            else:
                velocity_badge = "📦 Regular Mover"
                badge_color = "blue"

            order_count = int(r[7])
            order_share = round((order_count / grand_orders) * 100, 2)
            units_per_order = round(units / max(1, order_count), 2)

            results.append({
                "rank": idx,
                "asin": r[0] if r[0] != "N/A" else r[1],
                "sku": r[1],
                "title": r[2],
                "category": r[3],
                "units_sold": units,
                "revenue": rev,
                "avg_price": float(r[6]),
                "order_count": order_count,
                "order_share": order_share,
                "units_per_order": units_per_order,
                "active_days": active_days,
                "period_days": period_days,
                "consistency_pct": consistency_pct,
                "velocity_daily": velocity_per_day,
                "units_share": units_share,
                "revenue_share": revenue_share,
                "cumulative_share": round(min(100.0, cumulative_share_counter), 2),
                "has_revenue": has_revenue,
                "velocity_badge": velocity_badge,
                "badge_color": badge_color
            })

        return results

    def get_sales_trend(self, time_frame: str = "all_time", custom_start: Optional[str] = None, custom_end: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns time-series data for charting (Daily trends or Hourly for D-1).
        """
        if not self.has_data:
            return {"dates": [], "units": [], "revenue": []}

        date_sql = self._build_date_filter(time_frame, custom_start, custom_end)

        if time_frame == "d_minus_1":
            # Hourly breakdown for D-1
            query = f"""
                SELECT 
                    STRFTIME(order_date, '%H:00') as hour_str,
                    SUM(quantity) as units,
                    ROUND(SUM(total_amount), 2) as revenue
                FROM orders
                WHERE {date_sql}
                GROUP BY hour_str
                ORDER BY hour_str;
            """
        else:
            # Daily breakdown
            query = f"""
                SELECT 
                    date_str,
                    SUM(quantity) as units,
                    ROUND(SUM(total_amount), 2) as revenue
                FROM orders
                WHERE {date_sql}
                GROUP BY date_str
                ORDER BY date_str;
            """

        rows = self.con.execute(query).fetchall()
        total_units_trend = sum(int(r[1]) for r in rows) or 1
        total_rev_trend = sum(float(r[2]) for r in rows) or 1.0

        return {
            "labels": [r[0] for r in rows],
            "units": [int(r[1]) for r in rows],
            "revenue": [float(r[2]) for r in rows],
            "units_pct": [round((int(r[1]) / total_units_trend) * 100, 1) for r in rows],
            "revenue_pct": [round((float(r[2]) / total_rev_trend) * 100, 1) for r in rows]
        }

    def get_category_distribution(self, time_frame: str = "all_time", custom_start: Optional[str] = None, custom_end: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns category wise sales volume & revenue.
        """
        if not self.has_data:
            return []

        date_sql = self._build_date_filter(time_frame, custom_start, custom_end)
        rev_check = self.con.execute(f"SELECT COALESCE(SUM(total_amount), 0.0) FROM orders WHERE {date_sql}").fetchone()[0] or 0.0
        order_col = "total_revenue DESC" if rev_check > 0.01 else "total_units DESC"

        query = f"""
            SELECT 
                category,
                SUM(quantity) as total_units,
                ROUND(SUM(total_amount), 2) as total_revenue
            FROM orders
            WHERE {date_sql}
            GROUP BY category
            ORDER BY {order_col}
            LIMIT 10;
        """
        rows = self.con.execute(query).fetchall()
        total_rev = sum(float(r[2]) for r in rows)
        total_units = sum(int(r[1]) for r in rows) or 1
        has_rev = (total_rev > 0)

        if not has_rev:
            rows = sorted(rows, key=lambda x: int(x[1]), reverse=True)
            return [{
                "category": r[0],
                "units": int(r[1]),
                "revenue": float(r[2]),
                "share_pct": round((int(r[1]) / total_units) * 100, 1)
            } for r in rows]
        else:
            return [{
                "category": r[0],
                "units": int(r[1]),
                "revenue": float(r[2]),
                "share_pct": round((float(r[2]) / total_rev) * 100, 1)
            } for r in rows]

    def get_top_chart_items(
        self,
        time_frame: str = "all_time",
        metric: str = "units",
        limit: int = 10,
        status_filter: str = "delivered_only",
        custom_start: Optional[str] = None,
        custom_end: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Returns top 10 items formatted with both values AND percentage badges
        for dual-display horizontal bar charts.
        """
        items = self.get_top_selling_products(
            time_frame=time_frame,
            limit=limit,
            sort_by=metric,
            status_filter=status_filter,
            custom_start=custom_start,
            custom_end=custom_end
        )

        labels = []
        values = []
        percentages = []
        formatted_labels = []

        is_wms_mode = bool(items and not items[0].get("has_revenue", True))

        for idx, it in enumerate(items, 1):
            short_title = (it["title"][:22] + "...") if len(it["title"]) > 24 else it["title"]
            labels.append(f"#{idx} {short_title}")

            if metric == "units":
                val = it["units_sold"]
                pct = it["units_share"]
                val_str = f"{val:,} Units"
            else:
                if is_wms_mode:
                    val = it["order_count"]
                    pct = it["order_share"]
                    val_str = f"{val:,} Orders"
                else:
                    val = it["revenue"]
                    pct = it["revenue_share"]
                    val_str = f"₹ {val:,.0f}"

            values.append(val)
            percentages.append(pct)
            formatted_labels.append(f"{pct}% ({val_str})")

        return {
            "labels": labels,
            "values": values,
            "percentages": percentages,
            "formatted_labels": formatted_labels,
            "metric": metric,
            "is_wms_mode": is_wms_mode
        }

    def get_hourly_heatmap(self, time_frame: str = "all_time") -> List[Dict[str, Any]]:
        """
        Peak sales & dispatch hours (warehouse pick & pack planning).
        """
        if not self.has_data:
            return []

        query = """
            SELECT 
                CAST(STRFTIME(order_date, '%H') AS INTEGER) as order_hour,
                SUM(quantity) as units,
                COUNT(DISTINCT order_id) as orders
            FROM orders
            GROUP BY order_hour
            ORDER BY order_hour;
        """
        rows = self.con.execute(query).fetchall()
        return [{"hour": r[0], "units": int(r[1]), "orders": int(r[2])} for r in rows]

    def get_all_categories(self) -> List[str]:
        if not self.has_data:
            return []
        rows = self.con.execute("SELECT DISTINCT category FROM orders WHERE category IS NOT NULL ORDER BY category").fetchall()
        return [r[0] for r in rows]
