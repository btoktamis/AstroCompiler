# AstroCompiler (EOP and Space Weather Compiler)

AstroCompiler is a modern desktop application built with **Go** and **Wails (Vite + Javascript)** that compiles Earth Orientation Parameters (EOP) and space weather indices directly from raw primary scientific feeds (IERS Paris Observatory, USNO, GFZ Potsdam, SIDC Brussels, Penticton Canada, NOAA SWPC, and NASA) and generates standardized `EOP-All.txt` and `SW-All.txt` databases.

The project features high-performance parsing Go engines, an interactive HTML5/CSS3 graphical dashboard for visualization, offline compilation pipelines, and on-demand live compatibility checks against Celestrak.

---

## 1. Project Architecture

The repository is structured as a collection of reusable Go modules integrated into a desktop app, with legacy Python code kept in archive:

```
├── modules/
│   ├── spaceweather/              # Reusable Space Weather Go module
│   │   ├── go.mod
│   │   └── spaceweather.go        # Parsers, Bartels cycles, moving averages, and TXT/CSV exporters
│   └── eop/                       # Reusable EOP Go module
│       ├── go.mod
│       └── eop.go                 # Paris C04 and Bulletin A consolidation and DAT calculations
├── wailsapp/                      # Desktop UI Application (Wails)
│   ├── wails.json                 # Project configuration (outputs AstroCompiler.exe)
│   ├── main.go                    # App configuration (Window settings, bindings)
│   ├── app.go                     # Go-JS binding bridges (Compile, Save dialogs, On-Demand Verify)
│   ├── go.mod                     # Integrates local modules via replace directives
│   └── frontend/                  # Dashboard frontend (Vite + Vanilla JS/CSS)
│       ├── index.html
│       └── src/
│           ├── main.js            # Tab controller, filter grid, and dynamic SVG chart engine
│           └── style.css          # Catppuccin Mocha themed styling
└── legacy/                        # Legacy Python CLI compiler
    ├── main.py                    # Python command line launcher
    ├── requirements.txt           # CLI dependencies (requests only)
    └── spaceweather/              # Legacy CLI compilation engines
```

---

## 2. Setup & Compilation Guide

To download, compile, and run AstroCompiler on your local machine, you need to install the Go and Node.js development toolchains.

### 2.1. Prerequisites

Before building, install the following required packages:

1.  **Go Development Kit (v1.20 or newer)**:
    *   Used to compile the backend engines.
    *   Download from the official Go site: [go.dev/dl](https://go.dev/dl/)
2.  **Node.js (v18 or newer & npm)**:
    *   Used to compile frontend components and manage Vite assets.
    *   Download from the official Node.js site: [nodejs.org](https://nodejs.org/)
3.  **Wails CLI**:
    *   The framework used to package HTML/JS/CSS frontend with the Go backend.
    *   To install the Wails CLI, run the following command in your terminal:
        ```bash
        go install github.com/wailsapp/wails/v2/cmd/wails@latest
        ```
    *   Refer to the official Wails installation guide for help: [wails.io/docs/gettingstarted/installation](https://wails.io/docs/gettingstarted/installation)

### 2.2. Building the Desktop Application

Once you have installed the prerequisites, follow these steps to build the application:

1.  Open your terminal and navigate to the `wailsapp` directory:
    ```bash
    cd C:/0_Project_gravity/AstroCompiler/wailsapp
    ```
2.  Run the production build command:
    ```bash
    wails build
    ```
3.  The compiled desktop executable will be generated at:
    `wailsapp/build/bin/AstroCompiler.exe`

---

## 3. Primary Scientific Data Feeds

The backend retrieves raw data from primary international astronomical and geophysical services.

### 3.1. Space Weather Data Feeds

| Source | Organization | Purpose | URL |
| :--- | :--- | :--- | :--- |
| **Geomagnetic (Observed)** | GFZ Potsdam | Historical observations (Kp, ap, Ap, ISN, solar flux) | `https://www-app3.gfz-potsdam.de/kp_index/Kp_ap_Ap_SN_F107_since_1932.txt` |
| **Geomagnetic (Nowcast)** | GFZ Potsdam | Real-time preliminary measurements | `https://www-app3.gfz-potsdam.de/kp_index/Kp_ap_Ap_SN_F107_nowcast.txt` |
| **3-Hourly Forecast** | NOAA SWPC | 3-hourly Kp predictions (next 3 days) | `https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json` |
| **45-Day Forecast** | NOAA SWPC | 45-day daily Ap and F10.7 predictions | `https://services.swpc.noaa.gov/json/45-day-forecast.json` |
| **Monthly Sunspots** | NASA | 18-year monthly predicted Sunspot Numbers (50%) | `https://www.nasa.gov/wp-content/uploads/{yyyy}/{mm}/{month}{yyyy}ssn-prd.txt` |
| **Monthly Solar Flux** | NASA | 18-year monthly predicted F10.7 Adjusted (50%) | `https://www.nasa.gov/wp-content/uploads/{yyyy}/{mm}/{month}{yyyy}f10-prd.txt` |

### 3.2. Earth Orientation Parameters (EOP) Data Feeds

| Source | Organization | Purpose | URL |
| :--- | :--- | :--- | :--- |
| **Leap Seconds (DAT)** | USNO | Raw lookup file for TAI-UTC leap seconds | `https://maia.usno.navy.mil/ser7/tai-utc.dat` |
| **EOP 20 C04 (Standard)** | IERS Paris Observatory | Long-term standard EOP time series (1962-present) | `https://hpiers.obspm.fr/iers/eop/eopc04/eopc04.1962-now` |
| **EOP 20 C04 (Nutation)** | IERS Paris Observatory | Historical nutation parameters (dPsi, dEpsilon) | `https://hpiers.obspm.fr/iers/eop/eopc04/eopc04.dPsi_dEps.1962-now` |
| **Bulletin A (IAU 2000)** | USNO (IERS RS/PC) | Rapid Service/Predictions for x, y, UT1-UTC, dX, dY | `https://maia.usno.navy.mil/ser7/finals2000A.all` |
| **Bulletin A (IAU 1980)** | USNO (IERS RS/PC) | Rapid Service/Predictions for dPsi, dEpsilon | `https://maia.usno.navy.mil/ser7/finals.all` |

---

## 4. Mathematical & Physical Calculations

To generate the database, the engine implements several astronomical equations:

*   **Bartels Solar Rotation Number (BSRN)**: Continuous 27-day cycles corresponding to the Sun's rotation. The cycle system is counted from **February 8, 1832**.
*   **Earth-Sun Distance (J2000 Keplerian Approximation)**: Solar radio flux (F10.7) values are adjusted to 1 AU by computing Keplerian orbital distance $r$ using Mean Anomaly $g$ relative to the J2000 epoch.
*   **Indices Conversions**: Automatic conversions from Kp to 3-hourly ap amplitudes, mapping Ap daily averages to qualitative planetary character figures Cp, and scaling Cp to C9 single digits.
*   **Centered Moving Averages**: Computes 81-day centered and backward-looking solar flux averages. Missing measurements are solved by linear interpolation, and end-of-series boundary padding utilizes monthly NASA predicted models.
*   **DAT (Atomic Offset)**: Leap seconds are parsed dynamically from the USNO leap second tables to calculate proper time conversions based on Modified Julian Date (MJD).

---

## 5. Legacy Python CLI

The original Python-based command line parser is archived in the `legacy/` directory.

To run it, install the requests dependency:
```bash
cd C:/0_Project_gravity/AstroCompiler/legacy
pip install -r requirements.txt
```
To run EOP or Space Weather compiles from the command line:
```bash
python main.py --compile --output SW-All.txt --format txt --verbose
python main.py --compile-eop --eop-output eop19620101.txt --eop-legacy --verbose
```
