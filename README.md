# Offline Space Weather Compiler & Dashboard

This repository contains a modular Python application that compiles space weather indices directly from raw primary scientific feeds (GFZ Potsdam, SIDC Brussels, Penticton Canada, NOAA SWPC, and NASA) and generates the standardized `SW-All.txt` database from scratch, bypassing Celestrak.

The project features a **Data Engine** that performs all calculations, a **Command Line Interface (CLI)** for automation, and a **Desktop Dashboard (GUI)** for visualization and live compatibility checks.

---

## 1. Project Architecture

The codebase is split into a reusable backend package (`spaceweather`) and a main launcher:

*   **`main.py`**: Unified entry point. Launches the graphical desktop app by default, or runs in CLI mode if command-line arguments are provided.
*   **`spaceweather/engine.py`**: The core data engine. Handles raw downloads, parsing, math calculations, chronological data merging, file export (TXT/CSV), and verification.
*   **`spaceweather/cli.py`**: Exposes compiler settings, output formatting, and validation directly to the terminal.
*   **`spaceweather/gui.py`**: Desktop GUI using standard `tkinter` with a dark theme (Catppuccin color scheme). It displays compiler logs, provides a searchable grid of compiled values, and draws trend charts (using matplotlib or Canvas fallback).
*   **`requirements.txt`**: Minimal requirements (`requests`, `numpy`, `pandas`, `matplotlib`). The codebase automatically falls back to standard library modules if these are not installed, allowing zero-dependency execution.

---

## 2. Primary Scientific Data Feeds

The engine fetches and merges the following raw sources:

| Source | Organization | Purpose | URL |
| :--- | :--- | :--- | :--- |
| **Geomagnetic (Observed)** | GFZ Potsdam | Historical observations (Kp, ap, Ap, ISN, solar flux) | `https://www-app3.gfz-potsdam.de/kp_index/Kp_ap_Ap_SN_F107_since_1932.txt` |
| **Geomagnetic (Nowcast)** | GFZ Potsdam | Real-time preliminary measurements | `https://www-app3.gfz-potsdam.de/kp_index/Kp_ap_Ap_SN_F107_nowcast.txt` |
| **3-Hourly Forecast** | NOAA SWPC | 3-hourly Kp predictions (next 3 days) | `https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json` |
| **45-Day Forecast** | NOAA SWPC | 45-day daily Ap and F10.7 predictions | `https://services.swpc.noaa.gov/json/45-day-forecast.json` |
| **Monthly Sunspots** | NASA | 18-year monthly predicted Sunspot Numbers (50%) | `https://www.nasa.gov/wp-content/uploads/{yyyy}/{mm}/{month}{yyyy}ssn-prd.txt` |
| **Monthly Solar Flux** | NASA | 18-year monthly predicted F10.7 Adjusted (50%) | `https://www.nasa.gov/wp-content/uploads/{yyyy}/{mm}/{month}{yyyy}f10-prd.txt` |

*Note: The monthly prediction files on the NASA server are published dynamically in a subfolder corresponding to the publication month. The engine automatically crawls the URLs, falling back month-by-month if the current month's publication has not yet been uploaded.*

---

## 3. Mathematical & Physical Calculations

To generate the database, the engine implements several astro-physical equations:

### 3.1. Bartels Solar Rotation Number (BSRN)
Bartels Solar Rotation numbers divide time into continuous 27-day cycles corresponding to the Sun's rotation. The cycle system is counted from **February 8, 1832**.
Given a datetime object:
1.  Let $D$ be the integer number of days between the target date and the epoch `1832-02-08`.
2.  The Bartels Solar Rotation Number (BSRN) is:
    $$\text{BSRN} = 1 + \left\lfloor \frac{D}{27} \right\rfloor$$
3.  The Day within the rotation cycle (ND) ranges from 1 to 27:
    $$\text{ND} = 1 + (D \pmod{27})$$

### 3.2. Earth-Sun Distance (J2000 Orbital Mechanics)
Solar radio flux (F10.7) measurements are reported as either **Observed** (the raw signal received at Earth) or **Adjusted** (scaled to 1 Astronomical Unit). The conversion uses the inverse-square law:
$$S_{\text{obs}} = \frac{S_{\text{adj}}}{r^2}$$
To compute the Earth-Sun distance ratio $r$ (in AU) for any date:
1.  Compute the days $D_J$ (including decimals) since the **J2000.0 Epoch** (January 1, 2000, at 12:00 UTC).
2.  Compute the Earth's Mean Anomaly $g$ (in radians):
    $$g = \text{radians}(357.529 + 0.98560028 \times D_J)$$
3.  Compute the distance $r$ (in AU) using the Keplerian approximation:
    $$r = 1.00014 - 0.01671 \cos(g) - 0.00014 \cos(2g)$$

### 3.3. Geomagnetic Indices (Kp, ap, Ap, Cp, C9)
*   **ap (3-hour linear range)**: Map raw 3-hourly Kp floats to ap amplitudes using the standard conversion:

    | Kp | 0o | 0+ | 1- | 1o | 1+ | 2- | 2o | 2+ | 3- | 3o | 3+ | 4- | 4o | 4+ | 5- | 5o | 5+ | 6- | 6o | 6+ | 7- | 7o | 7+ | 8- | 8o | 8+ | 9- | 9o |
    |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
    | **ap** | 0 | 2 | 3 | 4 | 5 | 6 | 7 | 9 | 12 | 15 | 18 | 22 | 27 | 32 | 39 | 48 | 56 | 67 | 80 | 94 | 111 | 132 | 154 | 179 | 207 | 236 | 300 | 400 |

*   **Ap (Daily average)**: Arithmetic mean of the eight 3-hourly `ap` values, rounded to the nearest integer.
*   **Cp (Planetary Character Figure)**: Maps the daily sum of the eight 3-hourly `ap` indices ($\sum ap$) into a qualitative scale from `0.0` to `2.5` using the following step thresholds:
    *   $\sum ap \le 22 \rightarrow 0.0$
    *   $\sum ap \le 34 \rightarrow 0.1$
    *   $\sum ap \le 44 \rightarrow 0.2$
    *   $\sum ap \le 55 \rightarrow 0.3$
    *   $\sum ap \le 66 \rightarrow 0.4$
    *   $\sum ap \le 78 \rightarrow 0.5$
    *   $\sum ap \le 90 \rightarrow 0.6$
    *   $\sum ap \le 104 \rightarrow 0.7$
    *   $\sum ap \le 120 \rightarrow 0.8$
    *   $\sum ap \le 139 \rightarrow 0.9$
    *   $\sum ap \le 164 \rightarrow 1.0$
    *   $\sum ap \le 190 \rightarrow 1.1$
    *   $\sum ap \le 228 \rightarrow 1.2$
    *   $\sum ap \le 273 \rightarrow 1.3$
    *   $\sum ap \le 320 \rightarrow 1.4$
    *   $\sum ap \le 379 \rightarrow 1.5$
    *   $\sum ap \le 453 \rightarrow 1.6$
    *   $\sum ap \le 561 \rightarrow 1.7$
    *   $\sum ap \le 729 \rightarrow 1.8$
    *   $\sum ap \le 1119 \rightarrow 1.9$
    *   $\sum ap \le 1399 \rightarrow 2.0$
    *   $\sum ap \le 1699 \rightarrow 2.1$
    *   $\sum ap \le 1999 \rightarrow 2.2$
    *   $\sum ap \le 2399 \rightarrow 2.3$
    *   $\sum ap \le 3199 \rightarrow 2.4$
    *   $\ge 3200 \rightarrow 2.5$
*   **C9 (Single digit)**: Group Cp into ranges:
    *   $Cp \le 0.1 \rightarrow 0$
    *   $Cp \le 0.3 \rightarrow 1$
    *   $Cp \le 0.5 \rightarrow 2$
    *   $Cp \le 0.7 \rightarrow 3$
    *   $Cp \le 0.9 \rightarrow 4$
    *   $Cp \le 1.1 \rightarrow 5$
    *   $Cp \le 1.4 \rightarrow 6$
    *   $Cp \le 1.8 \rightarrow 7$
    *   $Cp \le 1.9 \rightarrow 8$
    *   $\ge 2.0 \rightarrow 9$

### 3.4. Moving Averages & Border Padding
The database includes 81-day centered (`Ctr81`) and 81-day backward-looking (`Lst81`) arithmetic averages of solar flux.
1.  **Interpolation**: The engine first scans the observed F10.7 values. Any missing measurements (flagged as `-1.0` in GFZ logs) are filled using linear interpolation.
2.  **Concatenation**: To solve edge-case boundary problems for the centered moving average (where dates near the end of observations require future data), the engine concatenates the Observed series and the Predicted series into a single continuous array before calculating averages.
3.  **Centered 81-Day Average**:
    $$\text{F10.7\_Ctr81}[t] = \frac{1}{81} \sum_{k=-40}^{40} \text{F10.7}[t+k]$$
4.  **Backward 81-Day Average**:
    $$\text{F10.7\_Lst81}[t] = \frac{1}{81} \sum_{k=-80}^{0} \text{F10.7}[t+k]$$

---

## 4. How to Use

Install dependencies (optional, fallbacks will run automatically if missing):
```bash
pip install -r requirements.txt
```

### 4.1. Graphical Desktop App (GUI)
Simply run the script with no arguments to open the dashboard:
```bash
python main.py
```
*   **COMPILER Tab**: Configure output path (TXT or CSV), cache folder, download & compile raw data, and run live verification reports.
*   **DATA VIEWER Tab**: Filter and search the database by dates or minimum geomagnetic activity (Kp).
*   **VISUALIZATION Tab**: Plot F10.7 Solar Flux and Ap index trends.

### 4.2. Command Line Compiler (CLI)
You can run automated compiles or verification routines:

*   **Compile legacy text file**:
    ```bash
    python main.py --compile --output SW-All.txt --format txt --verbose
    ```
*   **Compile CSV spreadsheet**:
    ```bash
    python main.py --compile --output SW-All.csv --format csv --verbose
    ```
*   **Run Celestrak Compatibility Check**:
    ```bash
    python main.py --verify
    ```

---

## 5. Reusing the Engine in Other Projects

You can import the module as a library. Here is an example script showing how to fetch and parse space weather:

```python
from spaceweather.engine import SpaceWeatherCompiler, get_earth_sun_distance

# Initialize compiler
compiler = SpaceWeatherCompiler(cache_dir="./cache")

# Run pipeline
data = compiler.compile()

# Access compiled observed records
print(f"Total Observed Days Compiled: {len(data['observed'])}")
last_record = data['observed'][-1]
print(f"Yesterday ({last_record['date']}) observed F10.7: {last_record['f107_obs']} sfu")

# Access predictions
print(f"Total Forecasted Days: {len(data['daily'])}")
first_forecast = data['daily'][0]
print(f"Today ({first_forecast['date']}) predicted Ap average: {first_forecast['ap_avg']} nT")

# Calculate Sun distance for a specific date
from datetime import datetime, timezone
dist = get_earth_sun_distance(datetime(2026, 6, 15, tzinfo=timezone.utc))
print(f"Earth-Sun distance on 2026-06-15 is: {dist:.6f} AU")
```
