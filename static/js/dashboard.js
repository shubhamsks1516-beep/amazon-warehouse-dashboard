// State Management
let currentFilter = 'all_time';
let currentStatus = 'delivered_only';
let currentSort = 'units';
let currentLimit = 50;
let currentSearch = '';
let currentCategory = 'all';
let customStart = null;
let customEnd = null;
let chartMetric = 'units'; // 'units' or 'revenue'
let currentProductsList = [];
let currentModalAsin = '';

let topProductsBarChartInstance = null;
let salesTrendChartInstance = null;
let categoryDonutChartInstance = null;
let searchDebounceTimer = null;

// Currency Formatter for Indian Rupees
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatINR(val) {
    if (!val || isNaN(val)) return '₹ 0';
    return '₹ ' + Number(val).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

// Compact Lakh / Crore notation
function formatCompactINR(val) {
    if (!val || isNaN(val)) return '₹ 0';
    const num = Number(val);
    if (num >= 10000000) {
        return '₹ ' + (num / 10000000).toFixed(2) + ' Cr';
    } else if (num >= 100000) {
        return '₹ ' + (num / 100000).toFixed(2) + ' Lakhs';
    } else if (num >= 1000) {
        return '₹ ' + (num / 1000).toFixed(1) + 'k';
    }
    return '₹ ' + num.toFixed(0);
}

// Toast Alert
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    const colorClass = type === 'success' ? 'border-emerald-500 bg-emerald-950/90 text-emerald-200' :
                       type === 'error' ? 'border-rose-500 bg-rose-950/90 text-rose-200' :
                       'border-blue-500 bg-blue-950/90 text-blue-200';
    
    toast.className = `p-3 rounded-xl border ${colorClass} text-xs font-semibold shadow-xl backdrop-blur-md flex items-center space-x-2 transition-all transform duration-300 translate-y-2`;
    toast.innerHTML = `<span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-4');
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// Lifecycle Init
document.addEventListener('DOMContentLoaded', async () => {
    if (window.lucide) {
        lucide.createIcons();
    }
    initDragAndDrop();
    
    // Close export dropdown when clicking outside
    document.addEventListener('click', (e) => {
        const menu = document.getElementById('exportMenu');
        const btn = document.getElementById('exportDropdownBtn');
        if (menu && btn && !btn.contains(e.target) && !menu.contains(e.target)) {
            menu.classList.add('hidden');
        }
    });

    await checkSystemStatus();
    await refreshDashboard();
});

// System Status Check
async function checkSystemStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        const label = document.getElementById('activeDatasetLabel');
        const rangeIndicator = document.getElementById('dateRangeIndicator');
        const clearBtn = document.getElementById('clearDataBtn');

        if (data.has_data) {
            if (clearBtn) clearBtn.classList.remove('hidden');
            label.textContent = `${data.dataset_name} • ${data.total_rows.toLocaleString()} Rows`;
            if (data.min_date && data.max_date && rangeIndicator) {
                rangeIndicator.textContent = `Span: ${data.min_date.slice(0, 10)} to ${data.max_date.slice(0, 10)}`;
            }
        } else {
            if (clearBtn) clearBtn.classList.add('hidden');
            label.textContent = 'No Raw Data Loaded';
            if (rangeIndicator) {
                rangeIndicator.textContent = 'Upload CSV/Excel to analyze';
            }
        }
    } catch (e) {
        console.error('Status check error:', e);
    }
}

// Reset / Clear Dashboard Back to Zero
async function clearDashboardData() {
    try {
        const res = await fetch('/api/clear', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Dashboard reset to clean 0 state. Waiting for upload.', 'info');
            await checkSystemStatus();
            await refreshDashboard();
        }
    } catch (e) {
        console.error('Clear error:', e);
        showToast('Error resetting dashboard', 'error');
    }
}

// Master Refresh Function
async function refreshDashboard() {
    await Promise.all([
        fetchSummary(),
        fetchTopSelling(),
        fetchTopBarChart(),
        fetchSalesTrend(),
        fetchCategories()
    ]);
    if (window.lucide) {
        lucide.createIcons();
    }
}

// 1. Fetch Executive Summary KPIs
async function fetchSummary() {
    try {
        const url = `/api/summary?time_frame=${currentFilter}&status_filter=${currentStatus}` +
            (customStart && customEnd ? `&custom_start=${customStart}&custom_end=${customEnd}` : '');
        const res = await fetch(url);
        const data = await res.json();

        if (data.empty) {
            document.getElementById('kpiUnits').textContent = '0';

            const kpiRevTitle = document.getElementById('kpiCard2Title');
            if (kpiRevTitle) kpiRevTitle.textContent = 'Total Revenue / Orders';
            const kpiRevVal = document.getElementById('kpiRevenue');
            if (kpiRevVal) {
                kpiRevVal.textContent = '0';
                kpiRevVal.className = 'text-3xl font-extrabold text-slate-400 font-mono tracking-tight';
            }
            const kpiRevHuman = document.getElementById('kpiRevenueHuman');
            if (kpiRevHuman) kpiRevHuman.textContent = '0 Orders';
            const kpiRevSub = document.getElementById('kpiRevenueSub');
            if (kpiRevSub) kpiRevSub.textContent = 'waiting for raw upload';

            const kpiOrdersTitle = document.getElementById('kpiCard3Title');
            if (kpiOrdersTitle) kpiOrdersTitle.textContent = 'Orders & Basket Size';
            const kpiOrdersVal = document.getElementById('kpiOrders');
            if (kpiOrdersVal) kpiOrdersVal.textContent = '0';
            const kpiOrdersUnit = document.getElementById('kpiOrdersUnit');
            if (kpiOrdersUnit) kpiOrdersUnit.textContent = 'Orders';
            const kpiCard3Sub = document.getElementById('kpiCard3Sub');
            if (kpiCard3Sub) kpiCard3Sub.innerHTML = `AOV: <strong class="text-slate-400 font-mono">₹ 0</strong> &nbsp;•&nbsp; SKUs: <strong class="text-slate-400 font-mono">0</strong>`;

            document.getElementById('kpiSkus').textContent = '0';
            document.getElementById('kpiCancelRate').textContent = '0%';

            const healthBadge = document.getElementById('kpiHealthBadge');
            if (healthBadge) {
                healthBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-800 text-slate-400 border border-slate-700';
                healthBadge.textContent = 'Ready for Upload';
            }

            const banner = document.getElementById('reportModeBanner');
            if (banner) banner.classList.add('hidden');

            const aiTimelineBadge = document.getElementById('aiInsightTimelineBadge');
            if (aiTimelineBadge) aiTimelineBadge.textContent = 'Status: Waiting for Raw Data File';

            const topTitle = document.getElementById('aiInsightTopProductTitle');
            if (topTitle) topTitle.textContent = 'No Product Data (Upload CSV/Excel to Begin)';

            const aiUnits = document.getElementById('aiInsightUnits');
            if (aiUnits) aiUnits.textContent = '0';
            const aiVolPct = document.getElementById('aiInsightVolumePct');
            if (aiVolPct) aiVolPct.textContent = '0%';
            const aiRevPct = document.getElementById('aiInsightRevPct');
            if (aiRevPct) aiRevPct.textContent = '0%';

            const aiDesc = document.getElementById('aiInsightDescription');
            if (aiDesc) {
                aiDesc.innerHTML = 'Please click <strong class="text-blue-400">"Upload Raw Data"</strong> above or drag & drop your warehouse CSV/Excel export to calculate high-selling products, volume shares, and run-rates.';
            }

            const aiTop5 = document.getElementById('aiTop5Share');
            if (aiTop5) aiTop5.textContent = '0%';
            const aiDays = document.getElementById('aiAnalyzedDays');
            if (aiDays) aiDays.textContent = '0 Days';

            const dateRange = document.getElementById('dateRangeIndicator');
            if (dateRange) dateRange.textContent = 'Upload CSV to start';

            return;
        }

        const isWmsMode = (data.has_revenue === false);

        // Clarification banner visibility
        const banner = document.getElementById('reportModeBanner');
        if (banner) {
            if (isWmsMode) {
                banner.classList.remove('hidden');
            } else {
                banner.classList.add('hidden');
            }
        }

        // Sort option label
        const sortRevOpt = document.getElementById('sortByRevOption');
        if (sortRevOpt) {
            sortRevOpt.textContent = isWmsMode ? 'Sort by: Customer Orders 📦' : 'Sort by: Revenue ₹';
        }

        document.getElementById('kpiUnits').textContent = data.total_units.toLocaleString();
        
        // Dynamic Card 2 (Revenue GMV vs Outbound Dispatches)
        const kpiRevTitle = document.getElementById('kpiCard2Title');
        const kpiRevVal = document.getElementById('kpiRevenue');
        const kpiRevHuman = document.getElementById('kpiRevenueHuman');
        const kpiRevSub = document.getElementById('kpiRevenueSub');

        if (isWmsMode) {
            if (kpiRevTitle) kpiRevTitle.textContent = 'Total Customer Orders';
            if (kpiRevVal) {
                kpiRevVal.textContent = `${data.total_orders.toLocaleString()} Orders`;
                kpiRevVal.className = 'text-3xl font-extrabold text-cyan-400 font-mono tracking-tight';
            }
            if (kpiRevHuman) kpiRevHuman.textContent = '100% Unique Outbound Picks';
            if (kpiRevSub) kpiRevSub.textContent = 'across dark store bins';
        } else {
            if (kpiRevTitle) kpiRevTitle.textContent = 'Total Revenue (GMV)';
            if (kpiRevVal) {
                kpiRevVal.textContent = formatINR(data.total_revenue);
                kpiRevVal.className = 'text-3xl font-extrabold text-emerald-400 font-mono tracking-tight';
            }
            if (kpiRevHuman) kpiRevHuman.textContent = formatCompactINR(data.total_revenue);
            if (kpiRevSub) kpiRevSub.textContent = 'gross merchandise value';
        }

        // Dynamic Card 3 (Orders & Basket Size)
        const kpiOrdersTitle = document.getElementById('kpiCard3Title');
        const kpiOrdersVal = document.getElementById('kpiOrders');
        const kpiOrdersUnit = document.getElementById('kpiOrdersUnit');
        const kpiCard3Sub = document.getElementById('kpiCard3Sub');

        if (isWmsMode) {
            if (kpiOrdersTitle) kpiOrdersTitle.textContent = 'Basket Density & SKUs';
            if (kpiOrdersVal) kpiOrdersVal.textContent = data.avg_units_per_order;
            if (kpiOrdersUnit) kpiOrdersUnit.textContent = 'Units / Order';
            if (kpiCard3Sub) kpiCard3Sub.innerHTML = `Avg Density: <strong class="text-amber-400 font-mono">${data.avg_units_per_order} pcs</strong> &nbsp;•&nbsp; SKUs: <strong class="text-slate-200 font-mono">${data.active_skus.toLocaleString()}</strong>`;
        } else {
            if (kpiOrdersTitle) kpiOrdersTitle.textContent = 'Orders & Basket Size';
            if (kpiOrdersVal) kpiOrdersVal.textContent = data.total_orders.toLocaleString();
            if (kpiOrdersUnit) kpiOrdersUnit.textContent = 'Orders';
            if (kpiCard3Sub) kpiCard3Sub.innerHTML = `AOV: <strong id="kpiAov" class="text-amber-400 font-mono">${formatINR(data.aov)}</strong> &nbsp;•&nbsp; SKUs: <strong class="text-slate-200 font-mono">${data.active_skus.toLocaleString()}</strong>`;
        }

        document.getElementById('kpiSkus').textContent = data.active_skus.toLocaleString();
        document.getElementById('kpiCancelRate').textContent = `${data.cancel_rate}%`;

        // Update AI Best-Seller Impact Intelligence Banner
        const aiTimelineBadge = document.getElementById('aiInsightTimelineBadge');
        if (aiTimelineBadge && data.start_period && data.end_period) {
            aiTimelineBadge.textContent = `Analyzed Duration: ${data.period_days} Days (${data.start_period.slice(0, 10)} to ${data.end_period.slice(0, 10)})`;
        }
        const topTitle = document.getElementById('aiInsightTopProductTitle');
        if (topTitle) topTitle.textContent = data.top1_name || 'No Product Data';
        
        const aiUnits = document.getElementById('aiInsightUnits');
        if (aiUnits) aiUnits.textContent = (data.top1_units || 0).toLocaleString();

        const aiVolPct = document.getElementById('aiInsightVolumePct');
        if (aiVolPct) aiVolPct.textContent = `${data.top1_units_share || 0}%`;

        const aiRevPct = document.getElementById('aiInsightRevPct');
        if (aiRevPct) aiRevPct.textContent = `${data.top1_rev_share || 0}%`;

        const aiDesc = document.getElementById('aiInsightDescription');
        if (aiDesc) {
            if (isWmsMode) {
                aiDesc.innerHTML = `Picked <strong class="text-white font-mono">${(data.top1_units || 0).toLocaleString()}</strong> units — contributing <strong class="text-blue-400 font-mono font-bold">${data.top1_units_share || 0}%</strong> of total store dispatch volume across <strong class="text-cyan-400 font-mono font-bold">${data.total_orders.toLocaleString()}</strong> customer orders.`;
            } else {
                aiDesc.innerHTML = `Sold <strong class="text-white font-mono">${(data.top1_units || 0).toLocaleString()}</strong> units — contributing <strong class="text-blue-400 font-mono font-bold">${data.top1_units_share || 0}%</strong> of your entire store's volume and <strong class="text-emerald-400 font-mono font-bold">${data.top1_rev_share || 0}%</strong> of gross revenue.`;
            }
        }

        const aiTop5 = document.getElementById('aiTop5Share');
        if (aiTop5) aiTop5.textContent = `${data.top5_units_share || 0}%`;

        const aiDays = document.getElementById('aiAnalyzedDays');
        if (aiDays) aiDays.textContent = `${data.period_days || 1} Days`;

        // Cancellation health badge
        const healthBadge = document.getElementById('kpiHealthBadge');
        if (data.cancel_rate < 3.0) {
            healthBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400';
            healthBadge.textContent = 'Top Fulfillment Grade';
        } else if (data.cancel_rate < 6.0) {
            healthBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-400';
            healthBadge.textContent = 'Moderate Returns';
        } else {
            healthBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-400';
            healthBadge.textContent = 'High Cancellations';
        }

        if (data.start_period && data.end_period) {
            document.getElementById('dateRangeIndicator').textContent = 
                `Active Span: ${data.start_period.slice(0, 10)} to ${data.end_period.slice(0, 10)} (${data.period_days} Days)`;
        }

    } catch (e) {
        console.error('Summary fetch error:', e);
    }
}

// 2. Fetch Top Selling Products
async function fetchTopSelling() {
    try {
        const tableBody = document.getElementById('topSellingTableBody');
        const url = `/api/top-selling?time_frame=${currentFilter}&sort_by=${currentSort}&limit=${currentLimit}` +
            `&category=${encodeURIComponent(currentCategory)}&status_filter=${currentStatus}` +
            (currentSearch ? `&search=${encodeURIComponent(currentSearch)}` : '') +
            (customStart && customEnd ? `&custom_start=${customStart}&custom_end=${customEnd}` : '');

        const res = await fetch(url);
        const data = await res.json();
        const items = data.items || [];
        currentProductsList = items;

        document.getElementById('tableRecordCount').textContent = `Showing ${items.length} high-selling products`;

        if (items.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center py-16 text-slate-400">
                        <div class="flex flex-col items-center justify-center space-y-3">
                            <div class="w-12 h-12 rounded-2xl bg-slate-800/80 flex items-center justify-center text-slate-400 border border-slate-700/80 shadow-md">
                                <i data-lucide="file-up" class="w-6 h-6 text-blue-400"></i>
                            </div>
                            <div class="text-sm font-bold text-white">No Raw Data Loaded (Clean Zero State)</div>
                            <p class="text-xs text-slate-400 max-w-sm">Please upload your Amazon WMS or Seller Central raw data file to see real-time high-selling rankings.</p>
                            <button onclick="openUploadModal()" class="mt-1 px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-xl text-xs font-bold transition-all shadow-md shadow-blue-600/30">
                                Upload Raw Data Now
                            </button>
                        </div>
                    </td>
                </tr>
            `;
            if (window.lucide) lucide.createIcons();
            return;
        }

        const hasRevenue = items.length > 0 && items[0].has_revenue !== false;

        // Dynamic Table Column Headers
        const thUnits = document.getElementById('thUnitsHeader');
        const thRev = document.getElementById('thRevenueHeader');
        const thPrice = document.getElementById('thPriceHeader');
        if (hasRevenue) {
            if (thUnits) thUnits.textContent = 'Units Sold (% Share)';
            if (thRev) thRev.textContent = 'Total GMV (₹) (% Share)';
            if (thPrice) thPrice.textContent = 'Avg Price';
        } else {
            if (thUnits) thUnits.textContent = 'Units Picked (% Share)';
            if (thRev) thRev.textContent = 'Customer Orders (% Share)';
            if (thPrice) thPrice.textContent = 'Units / Order';
        }

        const maxUnits = Math.max(...items.map(it => it.units_sold), 1);

        tableBody.innerHTML = items.map(it => {
            // Rank badge style
            let rankClass = 'rank-default';
            if (it.rank === 1) rankClass = 'rank-gold';
            else if (it.rank === 2) rankClass = 'rank-silver';
            else if (it.rank === 3) rankClass = 'rank-bronze';

            // Relative percentage bar
            const barWidth = Math.min(100, Math.round((it.units_sold / maxUnits) * 100));

            // Pareto 80/20 status
            const isTop80 = it.cumulative_share <= 80.0;
            const paretoBadge = isTop80 ? 
                `<span class="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 shadow-sm whitespace-nowrap" title="Generates 80% of store sales">Top 80% ⭐</span>` : 
                `<span class="inline-flex items-center px-2 py-1 rounded-full text-[10px] font-medium text-slate-400 bg-slate-800/90 border border-slate-700 whitespace-nowrap" title="Cumulative Share: ${it.cumulative_share}%">Tail (${it.cumulative_share}%)</span>`;

            // Category Badge with category specific colors & strict single line whitespace-nowrap
            let catColor = 'bg-slate-800/90 text-slate-200 border-slate-700';
            const catLower = (it.category || '').toLowerCase();
            if (catLower.includes('dairy') || catLower.includes('fresh')) {
                catColor = 'bg-sky-500/15 text-sky-300 border-sky-500/30';
            } else if (catLower.includes('fruit') || catLower.includes('veg')) {
                catColor = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
            } else if (catLower.includes('groc') || catLower.includes('staple')) {
                catColor = 'bg-amber-500/15 text-amber-300 border-amber-500/30';
            } else if (catLower.includes('snack') || catLower.includes('munch')) {
                catColor = 'bg-orange-500/15 text-orange-300 border-orange-500/30';
            } else if (catLower.includes('bever') || catLower.includes('drink')) {
                catColor = 'bg-purple-500/15 text-purple-300 border-purple-500/30';
            }

            // Dynamic Column 5 and 6 based on financial vs WMS report mode
            const col5Html = hasRevenue ? `
                <div class="font-mono font-bold text-sm text-emerald-400 whitespace-nowrap">${formatINR(it.revenue)}</div>
                <div class="flex items-center justify-end space-x-1 mt-0.5 whitespace-nowrap">
                    <span class="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20 whitespace-nowrap">
                        ${it.revenue_share}% GMV
                    </span>
                </div>
            ` : `
                <div class="font-mono font-bold text-sm text-cyan-300 whitespace-nowrap">${it.order_count.toLocaleString()} Orders</div>
                <div class="flex items-center justify-end space-x-1 mt-0.5 whitespace-nowrap">
                    <span class="text-[10px] font-bold text-cyan-300 bg-cyan-500/10 px-1.5 py-0.5 rounded border border-cyan-500/20 whitespace-nowrap">
                        ${it.order_share}% Orders
                    </span>
                </div>
            `;

            const col6Html = hasRevenue ? `
                <div class="font-mono text-slate-200 font-bold text-sm whitespace-nowrap">${formatINR(it.avg_price)}</div>
            ` : `
                <div class="inline-flex items-baseline space-x-1 whitespace-nowrap">
                    <span class="font-mono font-bold text-sm text-cyan-200">${it.units_per_order}</span>
                    <span class="text-[10px] text-slate-400 font-medium">pcs/ord</span>
                </div>
            `;

            // Velocity Badge styling with strict whitespace-nowrap
            let velocityBadgeColor = 'bg-amber-500/15 text-amber-300 border-amber-500/30';
            if (it.badge_color === 'emerald') {
                velocityBadgeColor = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
            } else if (it.badge_color === 'blue') {
                velocityBadgeColor = 'bg-blue-500/15 text-blue-300 border-blue-500/30';
            }

            const safeTitle = escapeHtml(it.title);
            const safeAsin = escapeHtml(it.asin);
            const safeSku = escapeHtml(it.sku);
            const safeCat = escapeHtml(it.category);

            return `
                <tr class="table-row-hover cursor-pointer border-b border-slate-800/40" onclick="openProductModal(${it.rank})" title="Click to view detailed SKU performance">
                    <td class="py-3 px-3 text-center whitespace-nowrap">
                        <span class="rank-badge ${rankClass}">#${it.rank}</span>
                    </td>
                    <td class="py-3 px-4 min-w-[320px]">
                        <div class="font-bold text-white text-xs max-w-sm truncate" title="${safeTitle}">${safeTitle}</div>
                        <div class="flex items-center space-x-2 mt-1 whitespace-nowrap">
                            <span class="font-mono text-[10px] text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded border border-amber-400/20 cursor-pointer hover:bg-amber-400/20 transition-all" onclick="event.stopPropagation(); copyText('${safeAsin}')" title="Click to copy ASIN">
                                ASIN: ${safeAsin}
                            </span>
                            <span class="font-mono text-[10px] text-slate-400 bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700">
                                SKU: ${safeSku}
                            </span>
                        </div>
                    </td>
                    <td class="py-3 px-4 text-center whitespace-nowrap">
                        <span class="inline-flex items-center justify-center px-3 py-1 rounded-lg text-[11px] font-semibold border whitespace-nowrap shadow-sm ${catColor}">
                            ${safeCat}
                        </span>
                    </td>
                    <td class="py-3 px-4 text-right whitespace-nowrap">
                        <div class="font-mono font-bold text-sm text-white whitespace-nowrap">${it.units_sold.toLocaleString()}</div>
                        <div class="flex items-center justify-end space-x-1 mt-0.5 whitespace-nowrap">
                            <span class="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded border border-blue-500/20 whitespace-nowrap">
                                ${it.units_share}% Volume
                            </span>
                        </div>
                        <div class="w-20 ml-auto bg-slate-800 h-1.5 rounded-full overflow-hidden mt-1.5">
                            <div class="bg-gradient-to-r from-blue-500 to-indigo-500 h-full rounded-full" style="width: ${barWidth}%"></div>
                        </div>
                    </td>
                    <td class="py-3 px-4 text-right whitespace-nowrap">
                        ${col5Html}
                    </td>
                    <td class="py-3 px-3 text-center whitespace-nowrap">
                        ${col6Html}
                    </td>
                    <td class="py-3 px-4 text-center whitespace-nowrap">
                        <div class="flex flex-col items-center justify-center space-y-1 whitespace-nowrap">
                            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold border shadow-sm whitespace-nowrap ${velocityBadgeColor}">
                                ${it.velocity_badge} <span class="ml-1 opacity-90 font-mono">(${it.velocity_daily}/day)</span>
                            </span>
                            <span class="text-[10px] text-slate-400 font-mono whitespace-nowrap">
                                Active in ${it.active_days}/${it.period_days} days (${it.consistency_pct}%)
                            </span>
                        </div>
                    </td>
                    <td class="py-3 px-3 text-center whitespace-nowrap">
                        ${paretoBadge}
                    </td>
                </tr>
            `;
        }).join('');

    } catch (e) {
        console.error('Top selling fetch error:', e);
    }
}

// 3. Fetch Top 10 High Selling Horizontal Bar Chart (With % and Values)
async function fetchTopBarChart() {
    try {
        const url = `/api/top-chart?time_frame=${currentFilter}&metric=${currentSort}&status_filter=${currentStatus}` +
            (customStart && customEnd ? `&custom_start=${customStart}&custom_end=${customEnd}` : '');
        const res = await fetch(url);
        const data = await res.json();

        const labels = data.labels || [];
        const values = data.values || [];
        const percentages = data.percentages || [];

        if (labels.length === 0) {
            if (topProductsBarChartInstance) {
                topProductsBarChartInstance.destroy();
                topProductsBarChartInstance = null;
            }
            const labelEl = document.getElementById('topBarMetricLabel');
            if (labelEl) labelEl.textContent = 'Waiting for upload';
            return;
        }

        const isWms = Boolean(data.is_wms_mode);
        let metricText = currentSort === 'units' ? 'Ranked by: Units Sold Share (%)' : 'Ranked by: Revenue Share (%)';
        if (isWms) {
            metricText = currentSort === 'units' ? 'Ranked by: Units Picked Share (%)' : 'Ranked by: Customer Orders Share (%)';
        }
        document.getElementById('topBarMetricLabel').textContent = metricText;

        const ctx = document.getElementById('topProductsBarChart').getContext('2d');
        if (topProductsBarChartInstance) {
            topProductsBarChartInstance.destroy();
        }

        const barColors = [
            '#F59E0B', '#F97316', '#38BDF8', '#6366F1', '#10B981',
            '#06B6D4', '#8B5CF6', '#EC4899', '#64748B', '#475569'
        ];

        const maxPct = Math.max(...percentages, 10);
        const xLimit = Math.ceil(maxPct * 1.55);

        topProductsBarChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    axis: 'y',
                    label: currentSort === 'units' ? 'Units Share (%)' : (isWms ? 'Orders Share (%)' : 'Revenue Share (%)'),
                    data: percentages,
                    backgroundColor: barColors.slice(0, labels.length),
                    borderRadius: 6,
                    borderSkipped: false
                }]
            },
            plugins: [{
                id: 'customBarLabels',
                afterDatasetsDraw(chart) {
                    const { ctx } = chart;
                    const meta = chart.getDatasetMeta(0);
                    meta.data.forEach((bar, index) => {
                        const formatted = data.formatted_labels ? data.formatted_labels[index] : `${percentages[index]}%`;
                        ctx.save();
                        ctx.fillStyle = index === 0 ? '#F59E0B' : index === 1 ? '#38BDF8' : index === 2 ? '#34D399' : '#CBD5E1';
                        ctx.font = 'bold 10px Plus Jakarta Sans, sans-serif';
                        ctx.textAlign = 'left';
                        ctx.textBaseline = 'middle';
                        ctx.fillText(formatted, bar.x + 8, bar.y);
                        ctx.restore();
                    });
                }
            }],
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: {
                        right: 120
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#0F172A',
                        borderColor: '#334155',
                        borderWidth: 1,
                        padding: 10,
                        titleFont: { size: 11, weight: 'bold' },
                        bodyFont: { size: 11 },
                        callbacks: {
                            label: function(ctx) {
                                const idx = ctx.dataIndex;
                                const pct = percentages[idx];
                                const val = values[idx];
                                let valStr = `${val.toLocaleString()} Units`;
                                if (currentSort !== 'units') {
                                    valStr = isWms ? `${val.toLocaleString()} Orders` : formatINR(val);
                                }
                                return `Store Contribution: ${pct}%  |  ${valStr}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        min: 0,
                        max: xLimit,
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: {
                            color: '#64748B',
                            font: { size: 9 },
                            callback: function(v) {
                                return v + '%';
                            }
                        }
                    },
                    y: {
                        grid: { display: false },
                        ticks: {
                            color: '#CBD5E1',
                            font: { size: 9.5, weight: '600' }
                        }
                    }
                }
            }
        });

    } catch (e) {
        console.error('Top bar chart error:', e);
    }
}

// 3. Sales Trend Chart
async function fetchSalesTrend() {
    try {
        const url = `/api/sales-trend?time_frame=${currentFilter}` +
            (customStart && customEnd ? `&custom_start=${customStart}&custom_end=${customEnd}` : '');
        const res = await fetch(url);
        const data = await res.json();

        const labels = data.labels || [];
        const values = chartMetric === 'units' ? data.units : data.revenue;

        if (labels.length === 0) {
            if (salesTrendChartInstance) {
                salesTrendChartInstance.destroy();
                salesTrendChartInstance = null;
            }
            return;
        }

        const chartTitle = currentFilter === 'd_minus_1' ? 
            'Hourly Sales & Peak Dispatch Rush (Yesterday D-1)' : 
            'Daily High-Selling Trendline';
        document.getElementById('trendChartTitle').textContent = chartTitle;

        const ctx = document.getElementById('salesTrendChart').getContext('2d');
        if (salesTrendChartInstance) {
            salesTrendChartInstance.destroy();
        }

        const gradient = ctx.createLinearGradient(0, 0, 0, 240);
        gradient.addColorStop(0, 'rgba(59, 130, 246, 0.45)');
        gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

        salesTrendChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: chartMetric === 'units' ? 'Units Sold' : 'Revenue (INR)',
                    data: values,
                    borderColor: '#38BDF8',
                    borderWidth: 2.5,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.35,
                    pointRadius: labels.length > 30 ? 0 : 3,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#38BDF8',
                    pointBorderColor: '#FFFFFF'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#0F172A',
                        borderColor: '#334155',
                        borderWidth: 1,
                        padding: 10,
                        titleFont: { size: 12, weight: 'bold' },
                        bodyFont: { size: 12 },
                        callbacks: {
                            label: function(ctx) {
                                const idx = ctx.dataIndex;
                                if (chartMetric === 'units') {
                                    const pct = data.units_pct ? data.units_pct[idx] : 0;
                                    return `Units: ${ctx.parsed.y.toLocaleString()} (${pct}% of period)`;
                                } else {
                                    const pct = data.revenue_pct ? data.revenue_pct[idx] : 0;
                                    return `Revenue: ${formatINR(ctx.parsed.y)} (${pct}% of period GMV)`;
                                }
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#64748B', font: { size: 10 } }
                    },
                    y: {
                        min: 0,
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: {
                            color: '#64748B',
                            font: { size: 10 },
                            callback: function(v) {
                                return chartMetric === 'units' ? v.toLocaleString() : '₹' + (v >= 1000 ? (v/1000).toFixed(0)+'k' : v);
                            }
                        }
                    }
                }
            }
        });

    } catch (e) {
        console.error('Trend chart error:', e);
    }
}

// 4. Categories Distribution Donut
async function fetchCategories() {
    try {
        const url = `/api/categories?time_frame=${currentFilter}` +
            (customStart && customEnd ? `&custom_start=${customStart}&custom_end=${customEnd}` : '');
        const res = await fetch(url);
        const data = await res.json();

        // Populate dropdown if not done
        const catSelect = document.getElementById('categorySelect');
        const prevSelected = catSelect.value;
        const allCats = data.all_categories || [];
        catSelect.innerHTML = '<option value="all">All Categories</option>' + 
            allCats.map(c => `<option value="${c}" ${c === prevSelected ? 'selected' : ''}>${c}</option>`).join('');

        const topCats = data.top_categories || [];

        if (topCats.length === 0) {
            if (categoryDonutChartInstance) {
                categoryDonutChartInstance.destroy();
                categoryDonutChartInstance = null;
            }
            return;
        }

        const ctx = document.getElementById('categoryDonutChart').getContext('2d');

        if (categoryDonutChartInstance) {
            categoryDonutChartInstance.destroy();
        }

        const colors = ['#F59E0B', '#3B82F6', '#10B981', '#8B5CF6', '#EC4899', '#06B6D4', '#64748B'];
        const hasRev = topCats.some(c => c.revenue > 0);

        categoryDonutChartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: topCats.map(c => `${c.category} (${c.share_pct}%)`),
                datasets: [{
                    data: topCats.map(c => (hasRev ? c.revenue : c.units)),
                    backgroundColor: colors.slice(0, topCats.length),
                    borderWidth: 2,
                    borderColor: '#111827'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '68%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#CBD5E1',
                            boxWidth: 10,
                            font: { size: 9.5, weight: '600' }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(ctx) {
                                const cat = topCats[ctx.dataIndex];
                                if (hasRev) {
                                    return `${cat.category}: ${cat.share_pct}% of GMV (${formatCompactINR(cat.revenue)} • ${cat.units.toLocaleString()} Units)`;
                                } else {
                                    return `${cat.category}: ${cat.share_pct}% of Total Volume (${cat.units.toLocaleString()} Units)`;
                                }
                            }
                        }
                    }
                }
            }
        });

    } catch (e) {
        console.error('Category donut error:', e);
    }
}

// Time Horizon Button Click
function setTimeFilter(tf) {
    currentFilter = tf;
    customStart = null;
    customEnd = null;

    // Reset active pill style
    ['d_minus_1', 'days_7', 'month_1', 'all_time', 'custom'].forEach(id => {
        const btn = document.getElementById(`btn-${id}`);
        if (btn) btn.classList.remove('active');
    });

    const activeBtn = document.getElementById(`btn-${tf}`);
    if (activeBtn) activeBtn.classList.add('active');

    const customBar = document.getElementById('customDateBar');
    if (customBar) customBar.classList.add('hidden');

    refreshDashboard();
}

// Custom Date Modal Toggle
function toggleCustomDateModal() {
    const customBar = document.getElementById('customDateBar');
    customBar.classList.toggle('hidden');
    const btn = document.getElementById('btn-custom');
    btn.classList.add('active');
    ['d_minus_1', 'days_7', 'month_1', 'all_time'].forEach(id => {
        document.getElementById(`btn-${id}`).classList.remove('active');
    });
}

function applyCustomDate() {
    const s = document.getElementById('customStartDate').value;
    const e = document.getElementById('customEndDate').value;
    if (!s || !e) {
        showToast('Please select both Start and End dates', 'error');
        return;
    }
    customStart = s;
    customEnd = e;
    currentFilter = 'custom';
    refreshDashboard();
    showToast(`Filter applied: ${s} to ${e}`, 'success');
}

// Status Filter Toggle
function setStatusFilter(status) {
    currentStatus = status;
    const delBtn = document.getElementById('status-delivered');
    const allBtn = document.getElementById('status-all');
    if (status === 'delivered_only') {
        delBtn.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-emerald-600/30 text-emerald-400 border border-emerald-500/30';
        allBtn.className = 'px-3 py-1 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200';
    } else {
        allBtn.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-blue-600/30 text-blue-400 border border-blue-500/30';
        delBtn.className = 'px-3 py-1 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200';
    }
    refreshDashboard();
}

// Chart Metric Switch
function setChartMetric(metric) {
    chartMetric = metric;
    const btnUnits = document.getElementById('btn-chart-units');
    const btnRev = document.getElementById('btn-chart-revenue');
    if (metric === 'units') {
        btnUnits.className = 'px-2.5 py-1 text-xs font-bold rounded-md bg-blue-600 text-white';
        btnRev.className = 'px-2.5 py-1 text-xs font-bold rounded-md text-slate-400 hover:text-white';
    } else {
        btnRev.className = 'px-2.5 py-1 text-xs font-bold rounded-md bg-blue-600 text-white';
        btnUnits.className = 'px-2.5 py-1 text-xs font-bold rounded-md text-slate-400 hover:text-white';
    }
    fetchSalesTrend();
}

// Table Filter Handlers
function handleSearch(val) {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        currentSearch = val;
        fetchTopSelling();
    }, 250);
}

function handleCategoryFilter(val) {
    currentCategory = val;
    fetchTopSelling();
}

function handleSortChange(val) {
    currentSort = val;
    fetchTopSelling();
    fetchTopBarChart();
}

function handleLimitChange(val) {
    currentLimit = parseInt(val, 10);
    fetchTopSelling();
}

// Multi-Format Export Handling (Excel, PDF, CSV)
function toggleExportMenu() {
    const menu = document.getElementById('exportMenu');
    if (menu) {
        menu.classList.toggle('hidden');
    }
}

function exportData(type) {
    const menu = document.getElementById('exportMenu');
    if (menu) menu.classList.add('hidden');

    const endpoint = type === 'excel' ? '/api/export-excel' :
                     type === 'pdf' ? '/api/export-pdf' : '/api/export-csv';

    const url = `${endpoint}?time_frame=${currentFilter}&sort_by=${currentSort}&status_filter=${currentStatus}` +
        `&category=${encodeURIComponent(currentCategory)}` +
        (currentSearch ? `&search=${encodeURIComponent(currentSearch)}` : '') +
        (customStart && customEnd ? `&custom_start=${customStart}&custom_end=${customEnd}` : '');

    window.location.href = url;
    
    const typeLabel = type === 'excel' ? 'Excel (.xlsx)' :
                      type === 'pdf' ? 'Executive PDF Report (.pdf)' : 'Raw CSV (.csv)';
    showToast(`Generating & downloading ${typeLabel}...`, 'success');
}

// Copy Helper
function copyText(txt) {
    navigator.clipboard.writeText(txt);
    showToast(`Copied: ${txt}`, 'success');
}

// Upload Modal & Drag-Drop Handling
function openUploadModal() {
    document.getElementById('uploadModal').classList.remove('hidden');
}

function closeUploadModal() {
    document.getElementById('uploadModal').classList.add('hidden');
    document.getElementById('uploadProgressContainer').classList.add('hidden');
}

function triggerFileInput() {
    document.getElementById('fileInput').click();
}

function initDragAndDrop() {
    const dropzone = document.getElementById('dropzone');
    if (!dropzone) return;

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dropzone-active');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dropzone-active');
        }, false);
    });

    dropzone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            uploadFile(files[0]);
        }
    });
}

function handleFileSelect(e) {
    if (e.target.files.length > 0) {
        uploadFile(e.target.files[0]);
    }
}

async function uploadFile(file) {
    const progressContainer = document.getElementById('uploadProgressContainer');
    const progressBar = document.getElementById('uploadProgressBar');
    const statusText = document.getElementById('uploadStatusText');
    const percentText = document.getElementById('uploadPercent');

    progressContainer.classList.remove('hidden');
    progressBar.style.width = '35%';
    percentText.textContent = '35%';
    statusText.textContent = `Uploading ${file.name} (${(file.size / (1024*1024)).toFixed(1)} MB)...`;

    const formData = new FormData();
    formData.append('file', file);

    try {
        progressBar.style.width = '70%';
        percentText.textContent = '70%';
        statusText.textContent = 'Processing & Indexing millions of rows with DuckDB engine...';

        const startTime = performance.now();
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        const duration = ((performance.now() - startTime) / 1000).toFixed(2);

        if (res.ok && data.status === 'success') {
            progressBar.style.width = '100%';
            percentText.textContent = '100%';
            statusText.textContent = `Completed in ${duration} seconds!`;
            
            showToast(`Parsed ${data.data.total_rows.toLocaleString()} rows in ${duration}s!`, 'success');
            
            setTimeout(() => {
                closeUploadModal();
                checkSystemStatus();
                refreshDashboard();
            }, 800);
        } else {
            throw new Error(data.detail || 'Upload failed');
        }
    } catch (e) {
        statusText.textContent = `Error: ${e.message}`;
        progressBar.style.width = '100%';
        progressBar.classList.add('bg-rose-500');
        showToast(`Upload failed: ${e.message}`, 'error');
    }
}

// Theme Toggle
function toggleTheme() {
    document.body.classList.toggle('light-theme');
    const isLight = document.body.classList.contains('light-theme');
    const btn = document.getElementById('themeBtn');
    btn.innerHTML = `<i data-lucide="${isLight ? 'moon' : 'sun'}" class="w-4 h-4"></i>`;
    if (window.lucide) lucide.createIcons();
    showToast(`Switched to ${isLight ? 'Light' : 'Dark'} mode`, 'info');
}

// Product Quick Peek Modal
function openProductModal(rank) {
    const item = currentProductsList.find(it => it.rank === rank);
    if (!item) return;

    currentModalAsin = item.asin;
    document.getElementById('modalProductRank').textContent = `#${item.rank}`;
    document.getElementById('modalProductTitle').textContent = item.title;
    document.getElementById('modalProductCategory').textContent = item.category;
    document.getElementById('modalProductAsin').textContent = `ASIN: ${item.asin}`;
    document.getElementById('modalProductSku').textContent = `SKU: ${item.sku}`;
    
    const isWms = (item.has_revenue === false);

    document.getElementById('modalProductUnits').textContent = item.units_sold.toLocaleString();
    document.getElementById('modalProductUnitsShare').textContent = `${item.units_share}% of total period volume`;
    
    const revLabel = document.getElementById('modalRevLabel');
    const revEl = document.getElementById('modalProductRevenue');
    const revShareEl = document.getElementById('modalProductRevShare');
    const priceLabel = document.getElementById('modalPriceLabel');
    const priceEl = document.getElementById('modalProductPrice');
    const priceSub = document.getElementById('modalPriceSub');

    if (isWms) {
        if (revLabel) revLabel.textContent = 'Customer Orders Picked';
        if (revEl) {
            revEl.textContent = `${item.order_count.toLocaleString()} Orders`;
            revEl.className = 'text-xl font-extrabold text-cyan-300 font-mono mt-0.5';
        }
        if (revShareEl) {
            revShareEl.textContent = `${item.order_share}% of total customer dispatches`;
            revShareEl.className = 'text-[11px] font-semibold text-cyan-400';
        }
        if (priceLabel) priceLabel.textContent = 'Basket Density';
        if (priceEl) priceEl.textContent = `${item.units_per_order} Units/Order`;
        if (priceSub) priceSub.textContent = 'avg units picked per dispatch';
    } else {
        if (revLabel) revLabel.textContent = 'Total Turnover (GMV)';
        if (revEl) {
            revEl.textContent = formatINR(item.revenue);
            revEl.className = 'text-xl font-extrabold text-emerald-400 font-mono mt-0.5';
        }
        if (revShareEl) {
            revShareEl.textContent = `${item.revenue_share}% of store GMV`;
            revShareEl.className = 'text-[11px] font-semibold text-emerald-300';
        }
        if (priceLabel) priceLabel.textContent = 'Average Unit Price';
        if (priceEl) priceEl.textContent = formatINR(item.avg_price);
        if (priceSub) priceSub.textContent = 'per order unit';
    }
    
    document.getElementById('modalProductVelocity').textContent = `${item.velocity_daily} /day`;
    document.getElementById('modalProductConsistency').textContent = `Sold in ${item.active_days} of ${item.period_days} days (${item.consistency_pct}%)`;

    const paretoEl = document.getElementById('modalProductPareto');
    if (item.cumulative_share <= 80.0) {
        paretoEl.className = 'px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30';
        paretoEl.textContent = 'Top 80% Driver ⭐';
    } else {
        paretoEl.className = 'px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-400 border border-slate-700';
        paretoEl.textContent = `Long Tail (${item.cumulative_share}%)`;
    }

    document.getElementById('productDetailModal').classList.remove('hidden');
    if (window.lucide) lucide.createIcons();
}

function closeProductModal() {
    const modal = document.getElementById('productDetailModal');
    if (modal) modal.classList.add('hidden');
}

function copyModalAsin() {
    if (currentModalAsin) {
        copyText(currentModalAsin);
    }
}

// Fullscreen / TV Display Mode Toggle
function toggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().then(() => {
            showToast('Warehouse TV / Fullscreen Display Enabled', 'info');
        }).catch(err => {
            console.error('Fullscreen request error:', err);
        });
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        }
    }
}
