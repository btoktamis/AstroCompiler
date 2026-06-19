import './style.css';
import { CompileSpaceWeather, CompileEOP, SelectDirectory } from '../wailsjs/go/main/App';
import { EventsOn } from '../wailsjs/runtime/runtime';

// Application State
let swData = null;
let eopData = null;
let currentTab = "spaceweather-panel";

// Data Viewer State
let viewerSource = "sw-obs";
let viewerPage = 1;
const pageSize = 50;
let filteredRecords = [];

// Tab Navigation
const navBtns = document.querySelectorAll(".nav-btn");
const panels = document.querySelectorAll(".panel");

navBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        navBtns.forEach(b => b.classList.remove("active"));
        panels.forEach(p => p.classList.remove("active"));
        
        btn.classList.add("active");
        const target = btn.getAttribute("data-target");
        const targetEl = document.getElementById(target);
        if (targetEl) {
            targetEl.classList.add("active");
            currentTab = target;
        }
        
        // Auto-refresh chart if we switch to charts panel
        if (target === "charts-panel") {
            triggerDrawChart();
        }
    });
});

// Setup Wails Log Event Listener
EventsOn("log", (data) => {
    const consoleId = data.category === "spaceweather" ? "sw-console" : "eop-console";
    const consoleEl = document.getElementById(consoleId);
    if (consoleEl) {
        const line = document.createElement("div");
        line.className = "console-line";
        
        const lower = data.message.toLowerCase();
        if (lower.includes("error") || lower.includes("failed")) {
            line.className += " error";
        } else if (lower.includes("success") || lower.includes("completed")) {
            line.className += " success";
        } else if (lower.includes("warning")) {
            line.className += " warning";
        } else if (lower.includes("fetching") || lower.includes("parsing")) {
            line.className += " system";
        } else {
            line.className += " info";
        }
        
        line.textContent = `[${new Date().toLocaleTimeString()}] ${data.message}`;
        consoleEl.appendChild(line);
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }
});

// Helper for Clear buttons
document.getElementById("btn-sw-clear").addEventListener("click", () => {
    document.getElementById("sw-console").innerHTML = '<div class="console-line system">Console cleared. Waiting...</div>';
});
document.getElementById("btn-eop-clear").addEventListener("click", () => {
    document.getElementById("eop-console").innerHTML = '<div class="console-line system">Console cleared. Waiting...</div>';
});

// Directory Browser Setup
document.getElementById("btn-sw-browse").addEventListener("click", async () => {
    try {
        const dir = await SelectDirectory();
        if (dir) {
            const format = document.getElementById("sw-format").value;
            document.getElementById("sw-output").value = dir + "/SW-All." + format;
        }
    } catch (err) {
        console.error(err);
    }
});

document.getElementById("btn-eop-browse").addEventListener("click", async () => {
    try {
        const dir = await SelectDirectory();
        if (dir) {
            const format = document.getElementById("eop-format").value;
            document.getElementById("eop-output").value = dir + "/EOP-All." + format;
        }
    } catch (err) {
        console.error(err);
    }
});

// Auto suffix outputs on dropdown change
document.getElementById("sw-format").addEventListener("change", (e) => {
    const val = document.getElementById("sw-output").value;
    if (val) {
        const ext = e.target.value;
        const newPath = val.substring(0, val.lastIndexOf(".")) + "." + ext;
        document.getElementById("sw-output").value = newPath;
    }
});

document.getElementById("eop-format").addEventListener("change", (e) => {
    const val = document.getElementById("eop-output").value;
    if (val) {
        const ext = e.target.value;
        const newPath = val.substring(0, val.lastIndexOf(".")) + "." + ext;
        document.getElementById("eop-output").value = newPath;
    }
});

// Compilation triggers
document.getElementById("btn-sw-compile").addEventListener("click", async () => {
    const format = document.getElementById("sw-format").value;
    const cacheDir = document.getElementById("sw-cache").value || "./cache";
    const outPath = document.getElementById("sw-output").value || "";
    
    // Toggle UI state
    const btn = document.getElementById("btn-sw-compile");
    const spinner = document.getElementById("sw-spinner");
    btn.disabled = true;
    spinner.classList.remove("hide");
    
    // Clear logs
    const consoleEl = document.getElementById("sw-console");
    consoleEl.innerHTML = '<div class="console-line system">Starting new Space Weather compilation pipeline...</div>';
    
    try {
        const res = await CompileSpaceWeather(true, cacheDir, outPath, format);
        if (res && res.success) {
            swData = res;
            
            // Show metrics cards
            document.getElementById("sw-stats-card").classList.remove("hide");
            document.getElementById("sw-stat-observed").textContent = res.observed_count;
            document.getElementById("sw-stat-daily").textContent = res.daily_count;
            document.getElementById("sw-stat-monthly").textContent = res.monthly_count;
            
            const matchRate = res.verification ? (res.verification.obs_match_rate * 100).toFixed(2) + "%" : "N/A";
            document.getElementById("sw-stat-match").textContent = matchRate;
            
            // Sync with Data Viewer
            updateViewerSourceOptions();
            applyFilters();
            triggerDrawChart();
        }
    } catch (err) {
        console.error(err);
        const line = document.createElement("div");
        line.className = "console-line error";
        line.textContent = `CRITICAL COMPILER ERROR: ${err.message || err}`;
        consoleEl.appendChild(line);
    } finally {
        btn.disabled = false;
        spinner.classList.add("hide");
    }
});

document.getElementById("btn-eop-compile").addEventListener("click", async () => {
    const format = document.getElementById("eop-format").value;
    const mode = document.getElementById("eop-mode").value;
    const cacheDir = document.getElementById("eop-cache").value || "./cache";
    const outPath = document.getElementById("eop-output").value || "";
    const isOffline = mode === "offline";
    
    const btn = document.getElementById("btn-eop-compile");
    const spinner = document.getElementById("eop-spinner");
    btn.disabled = true;
    spinner.classList.remove("hide");
    
    const consoleEl = document.getElementById("eop-console");
    consoleEl.innerHTML = '<div class="console-line system">Starting new EOP compilation pipeline...</div>';
    
    try {
        const res = await CompileEOP(isOffline, cacheDir, outPath, format);
        if (res && res.success) {
            eopData = res;
            
            document.getElementById("eop-stats-card").classList.remove("hide");
            document.getElementById("eop-stat-observed").textContent = res.observed_count;
            document.getElementById("eop-stat-predicted").textContent = res.predicted_count;
            
            const matchRate = res.verification ? (res.verification.obs_match_rate * 100).toFixed(2) + "%" : "N/A";
            const matchRatePred = res.verification ? (res.verification.pred_match_rate * 100).toFixed(2) + "%" : "N/A";
            document.getElementById("eop-stat-match").textContent = matchRate;
            document.getElementById("eop-stat-match-pred").textContent = matchRatePred;
            
            updateViewerSourceOptions();
            applyFilters();
        }
    } catch (err) {
        console.error(err);
        const line = document.createElement("div");
        line.className = "console-line error";
        line.textContent = `CRITICAL COMPILER ERROR: ${err.message || err}`;
        consoleEl.appendChild(line);
    } finally {
        btn.disabled = false;
        spinner.classList.add("hide");
    }
});

// Data Viewer Controls
const viewerSourceSelect = document.getElementById("viewer-source");
viewerSourceSelect.addEventListener("change", (e) => {
    viewerSource = e.target.value;
    viewerPage = 1;
    
    // Toggle Kp filter visibility (only for Space Weather)
    const swFilterFields = document.querySelectorAll(".sw-filter-fields");
    if (viewerSource.startsWith("sw-")) {
        swFilterFields.forEach(f => f.classList.remove("hide"));
    } else {
        swFilterFields.forEach(f => f.classList.add("hide"));
    }
    
    applyFilters();
});

document.getElementById("btn-apply-filters").addEventListener("click", () => {
    viewerPage = 1;
    applyFilters();
});

document.getElementById("btn-reset-filters").addEventListener("click", () => {
    document.getElementById("filter-date-start").value = "";
    document.getElementById("filter-date-end").value = "";
    document.getElementById("filter-kp").value = "";
    viewerPage = 1;
    applyFilters();
});

document.getElementById("btn-page-prev").addEventListener("click", () => {
    if (viewerPage > 1) {
        viewerPage--;
        renderTable();
    }
});

document.getElementById("btn-page-next").addEventListener("click", () => {
    const maxPage = Math.ceil(filteredRecords.length / pageSize) || 1;
    if (viewerPage < maxPage) {
        viewerPage++;
        renderTable();
    }
});

// Update source availability
function updateViewerSourceOptions() {
    // Enable or disable based on data presence
    const opts = viewerSourceSelect.options;
    for (let i = 0; i < opts.length; i++) {
        const val = opts[i].value;
        if (val.startsWith("sw-")) {
            opts[i].disabled = !swData;
        } else if (val.startsWith("eop-")) {
            opts[i].disabled = !eopData;
        }
    }
}

// Filtering logic
function applyFilters() {
    let sourceData = [];
    
    if (viewerSource === "sw-obs" && swData) {
        sourceData = swData.observed || [];
    } else if (viewerSource === "sw-pred" && swData) {
        sourceData = swData.daily || [];
    } else if (viewerSource === "sw-month" && swData) {
        sourceData = swData.monthly || [];
    } else if (viewerSource === "eop-obs" && eopData) {
        sourceData = eopData.observed || [];
    } else if (viewerSource === "eop-pred" && eopData) {
        sourceData = eopData.predicted || [];
    }
    
    const startVal = document.getElementById("filter-date-start").value;
    const endVal = document.getElementById("filter-date-end").value;
    const kpVal = parseInt(document.getElementById("filter-kp").value);
    
    filteredRecords = sourceData.filter(r => {
        // Date check
        if (startVal && r.date < startVal) return false;
        if (endVal && r.date > endVal) return false;
        
        // Kp check (Only SW observed / predictions have KpVals)
        if (kpVal && r.kp_vals) {
            // Find max Kp in 3-hourly values
            const maxKp = Math.max(...r.kp_vals);
            if (maxKp < kpVal) return false;
        }
        
        return true;
    });
    
    renderTable();
}

// Table rendering
function renderTable() {
    const table = document.getElementById("data-table");
    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");
    const counter = document.getElementById("table-row-count");
    
    thead.innerHTML = "";
    tbody.innerHTML = "";
    
    const maxPage = Math.ceil(filteredRecords.length / pageSize) || 1;
    if (viewerPage > maxPage) viewerPage = maxPage;
    
    document.getElementById("page-num").textContent = `Page ${viewerPage} of ${maxPage}`;
    counter.textContent = `Showing ${filteredRecords.length} records`;
    
    if (filteredRecords.length === 0) {
        tbody.innerHTML = `<tr><td class="empty-state" colspan="100">No records match the filter criteria.</td></tr>`;
        return;
    }
    
    // Set headers dynamically
    let headers = [];
    if (viewerSource.startsWith("sw-")) {
        if (viewerSource === "sw-month") {
            headers = ["DATE", "BSRN", "ND", "ISN", "F10.7_ADJ", "F10.7_OBS"];
        } else {
            headers = ["DATE", "BSRN", "ND", "KP_MAX", "AP_AVG", "CP", "C9", "ISN", "F10.7_ADJ", "F10.7_OBS"];
        }
    } else {
        headers = ["DATE", "MJD", "X", "Y", "UT1-UTC", "LOD", "dPSI", "dEPS", "dX", "dY", "DAT"];
    }
    
    let headerHtml = "<tr>";
    headers.forEach(h => {
        headerHtml += `<th>${h}</th>`;
    });
    headerHtml += "</tr>";
    thead.innerHTML = headerHtml;
    
    // Slice page
    const startIdx = (viewerPage - 1) * pageSize;
    const pageData = filteredRecords.slice(startIdx, startIdx + pageSize);
    
    pageData.forEach(r => {
        let rowHtml = "<tr>";
        if (viewerSource.startsWith("sw-")) {
            const dateStr = r.date || `${r.year}-${String(r.month).padStart(2,'0')}-${String(r.day).padStart(2,'0')}`;
            if (viewerSource === "sw-month") {
                rowHtml += `
                    <td>${dateStr}</td>
                    <td>${r.bsrn}</td>
                    <td>${r.nd}</td>
                    <td>${r.isn}</td>
                    <td>${r.f107_adj.toFixed(1)}</td>
                    <td>${r.f107_obs.toFixed(1)}</td>
                `;
            } else {
                const maxKp = r.kp_vals ? (Math.max(...r.kp_vals) / 10).toFixed(1) : "N/A";
                const apSum = r.ap_vals ? r.ap_vals.reduce((a,b)=>a+b, 0) : 0;
                
                // Cp & C9 calculations
                const cpVal = r.ap_vals ? apSumToCp(apSum) : 0.0;
                const c9Val = r.ap_vals ? cpToC9(cpVal) : 0;
                
                rowHtml += `
                    <td>${dateStr}</td>
                    <td>${r.bsrn}</td>
                    <td>${r.nd}</td>
                    <td>${maxKp}</td>
                    <td>${r.ap_avg}</td>
                    <td>${cpVal.toFixed(1)}</td>
                    <td>${c9Val}</td>
                    <td>${r.isn}</td>
                    <td>${r.f107_adj.toFixed(1)}</td>
                    <td>${r.f107_obs.toFixed(1)}</td>
                `;
            }
        } else {
            const dateStr = r.date || `${r.year}-${String(r.month).padStart(2,'0')}-${String(r.day).padStart(2,'0')}`;
            rowHtml += `
                <td>${dateStr}</td>
                <td>${r.mjd}</td>
                <td>${r.x.toFixed(6)}</td>
                <td>${r.y.toFixed(6)}</td>
                <td>${r.ut1_utc.toFixed(7)}</td>
                <td>${r.lod.toFixed(7)}</td>
                <td>${r.dpsi.toFixed(6)}</td>
                <td>${r.deps.toFixed(6)}</td>
                <td>${r.dx.toFixed(6)}</td>
                <td>${r.dy.toFixed(6)}</td>
                <td>${r.dat}</td>
            `;
        }
        rowHtml += "</tr>";
        tbody.innerHTML += rowHtml;
    });
}

// Indices conversions for JS table fallback
function apSumToCp(sum) {
    if (sum <= 22) return 0.0;
    if (sum <= 34) return 0.1;
    if (sum <= 44) return 0.2;
    if (sum <= 55) return 0.3;
    if (sum <= 66) return 0.4;
    if (sum <= 78) return 0.5;
    if (sum <= 90) return 0.6;
    if (sum <= 104) return 0.7;
    if (sum <= 120) return 0.8;
    if (sum <= 139) return 0.9;
    if (sum <= 164) return 1.0;
    if (sum <= 190) return 1.1;
    if (sum <= 228) return 1.2;
    if (sum <= 273) return 1.3;
    if (sum <= 320) return 1.4;
    if (sum <= 379) return 1.5;
    if (sum <= 453) return 1.6;
    if (sum <= 561) return 1.7;
    if (sum <= 729) return 1.8;
    if (sum <= 1119) return 1.9;
    if (sum <= 1399) return 2.0;
    if (sum <= 1699) return 2.1;
    if (sum <= 1999) return 2.2;
    if (sum <= 2399) return 2.3;
    if (sum <= 3199) return 2.4;
    return 2.5;
}

function cpToC9(cp) {
    if (cp <= 0.1) return 0;
    if (cp <= 0.3) return 1;
    if (cp <= 0.5) return 2;
    if (cp <= 0.7) return 3;
    if (cp <= 0.9) return 4;
    if (cp <= 1.1) return 5;
    if (cp <= 1.4) return 6;
    if (cp <= 1.8) return 7;
    if (cp <= 1.9) return 8;
    return 9;
}

// Chart controls
document.getElementById("btn-draw-chart").addEventListener("click", () => {
    triggerDrawChart();
});

function triggerDrawChart() {
    const metric = document.getElementById("chart-metric").value;
    const range = document.getElementById("chart-range").value;
    drawChart(metric, range);
}

// SVG Dynamic Chart Rendering
function drawChart(metric, range) {
    const container = document.getElementById("chart-svg-container");
    if (!swData || !swData.observed) {
        container.innerHTML = `<div class="empty-state">Compile Space Weather data to render charts.</div>`;
        return;
    }
    
    // 1. Prepare data based on selection
    let data = [];
    if (range === "30" || range === "90" || range === "365") {
        const days = parseInt(range);
        const obs = swData.observed.slice(-days);
        const pred = swData.daily || [];
        data = [...obs, ...pred];
    } else {
        const obsFiltered = swData.observed.filter(r => r.day === 1);
        const pred = swData.monthly || [];
        data = [...obsFiltered, ...pred];
    }
    
    const width = 1100;
    const height = 400;
    const margin = { top: 30, right: 40, bottom: 40, left: 60 };
    
    const chartW = width - margin.left - margin.right;
    const chartH = height - margin.top - margin.bottom;
    
    let yValueFn;
    let title = "";
    if (metric === "f107") {
        yValueFn = r => r.f107_obs;
        title = "F10.7 Solar Radio Flux Trend";
        document.getElementById("chart-title").textContent = title;
    } else if (metric === "ap") {
        yValueFn = r => r.ap_avg;
        title = "Ap Geomagnetic Index Trend";
        document.getElementById("chart-title").textContent = title;
    } else {
        yValueFn = r => r.isn;
        title = "Sunspot Number (ISN) Trend";
        document.getElementById("chart-title").textContent = title;
    }
    
    const validData = data.filter(r => yValueFn(r) >= 0);
    if (validData.length === 0) {
        container.innerHTML = `<div class="empty-state">No valid records found for selection.</div>`;
        return;
    }
    
    const yVals = validData.map(r => yValueFn(r));
    const minY = Math.min(...yVals);
    const maxY = Math.max(...yVals);
    const rangeY = (maxY - minY) || 1;
    
    const padMinY = Math.max(0, minY - rangeY * 0.1);
    const padMaxY = maxY + rangeY * 0.1;
    const scaleY = padMaxY - padMinY;
    
    const getX = idx => margin.left + (idx / (validData.length - 1)) * chartW;
    const getY = val => margin.top + chartH - ((val - padMinY) / scaleY) * chartH;
    
    let svgContent = `<svg class="chart-svg" viewBox="0 0 ${width} ${height}">`;
    
    // Gradients definitions
    svgContent += `
        <defs>
            <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.3"/>
                <stop offset="100%" stop-color="var(--accent)" stop-opacity="0.0"/>
            </linearGradient>
            <linearGradient id="chartLineGrad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stop-color="var(--accent-secondary)"/>
                <stop offset="100%" stop-color="var(--accent)"/>
            </linearGradient>
        </defs>
    `;
    
    // Y Axis lines and Grid Ticks
    const gridDivs = 5;
    for (let i = 0; i <= gridDivs; i++) {
        const val = padMinY + (i / gridDivs) * scaleY;
        const y = getY(val);
        svgContent += `
            <line class="chart-grid" x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}"/>
            <text class="chart-text" x="${margin.left - 10}" y="${y + 4}" text-anchor="end">${Math.round(val)}</text>
        `;
    }
    
    // X Axis lines and Grid Ticks
    const tickDivs = 6;
    for (let i = 0; i <= tickDivs; i++) {
        const idx = Math.round((i / tickDivs) * (validData.length - 1));
        if (idx >= 0 && idx < validData.length) {
            const r = validData[idx];
            const x = getX(idx);
            svgContent += `
                <line class="chart-grid" x1="${x}" y1="${margin.top}" x2="${x}" y2="${height - margin.bottom}"/>
                <text class="chart-text" x="${x}" y="${height - margin.bottom + 16}" text-anchor="middle">${r.date}</text>
            `;
        }
    }
    
    // Draw paths
    let pointsObs = [];
    let pointsPred = [];
    
    validData.forEach((r, idx) => {
        const x = getX(idx);
        const y = getY(yValueFn(r));
        const isPred = r.source === "NOAA_PRED" || r.source === "NASA_PRED" || r.source === "D" || r.source === "M";
        if (!isPred) {
            pointsObs.push({x, y});
        } else {
            if (pointsObs.length > 0 && pointsPred.length === 0) {
                pointsPred.push(pointsObs[pointsObs.length - 1]);
            }
            pointsPred.push({x, y});
        }
    });
    
    // Draw observed Area and Line
    if (pointsObs.length > 1) {
        const pathLine = "M " + pointsObs.map(p => `${p.x},${p.y}`).join(" L ");
        const pathArea = pathLine + ` L ${pointsObs[pointsObs.length - 1].x},${height - margin.bottom} L ${pointsObs[0].x},${height - margin.bottom} Z`;
        
        svgContent += `<path class="chart-area" d="${pathArea}" fill="url(#chartGradient)"/>`;
        svgContent += `<path class="chart-line" d="${pathLine}" stroke="url(#chartLineGrad)"/>`;
    }
    
    // Draw predicted line (dashed)
    if (pointsPred.length > 1) {
        const pathLinePred = "M " + pointsPred.map(p => `${p.x},${p.y}`).join(" L ");
        svgContent += `<path class="chart-line chart-line-pred" d="${pathLinePred}" stroke="var(--accent)"/>`;
    }
    
    // Base axes
    svgContent += `
        <line class="chart-axis" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}"/>
        <line class="chart-axis" x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}"/>
    `;
    
    // Draw interaction circles (if count is small)
    if (validData.length <= 150) {
        validData.forEach((r, idx) => {
            const x = getX(idx);
            const val = yValueFn(r);
            const y = getY(val);
            const isPred = r.source === "NOAA_PRED" || r.source === "NASA_PRED" || r.source === "D" || r.source === "M";
            const color = isPred ? "var(--accent)" : "var(--accent-secondary)";
            
            svgContent += `
                <circle class="chart-dot" cx="${x}" cy="${y}" r="4" fill="${color}" stroke="var(--bg-crust)" 
                    data-date="${r.date}" data-val="${val}" data-src="${r.source || 'OBS'}"/>
            `;
        });
    }
    
    svgContent += `</svg>`;
    container.innerHTML = svgContent;
    
    // Tooltip listeners setup
    const dots = container.querySelectorAll(".chart-dot");
    let tooltip = document.getElementById("chart-tooltip");
    if (!tooltip) {
        tooltip = document.createElement("div");
        tooltip.id = "chart-tooltip";
        tooltip.className = "chart-tooltip hide";
        document.body.appendChild(tooltip);
    }
    
    dots.forEach(dot => {
        dot.addEventListener("mouseenter", (e) => {
            const date = dot.getAttribute("data-date");
            const val = parseFloat(dot.getAttribute("data-val")).toFixed(1);
            const src = dot.getAttribute("data-src");
            
            tooltip.innerHTML = `
                <strong>Date:</strong> ${date}<br/>
                <strong>Value:</strong> ${val}<br/>
                <strong>Source:</strong> ${src}
            `;
            tooltip.classList.remove("hide");
        });
        
        dot.addEventListener("mousemove", (e) => {
            tooltip.style.left = (e.pageX + 12) + "px";
            tooltip.style.top = (e.pageY - 12) + "px";
        });
        
        dot.addEventListener("mouseleave", () => {
            tooltip.classList.add("hide");
        });
    });
    
    // Legend indicators
    const legendEl = document.getElementById("chart-legend");
    legendEl.innerHTML = `
        <div class="legend-item">
            <span class="legend-color" style="background-color: var(--accent-secondary)"></span>
            <span>Observed Series</span>
        </div>
        <div class="legend-item">
            <span class="legend-color" style="background-color: var(--accent); border: 1px dashed var(--bg-crust)"></span>
            <span>Forecasted / Predicted</span>
        </div>
    `;
}
