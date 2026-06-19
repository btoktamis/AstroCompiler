# Implementation Plan: Offline Space Weather Compiler & Desktop UI

This plan outlines the architecture and steps to build a local, self-contained Python module that compiles space weather data directly from raw primary sources (GFZ Potsdam, SIDC, Penticton, NOAA, and NASA) and reproduces the `SW-All.txt` file format from scratch, bypassing Celestrak.

The module will include:
1. **A Data Compilation Engine** that fetches raw data, parses various text/JSON formats, computes derived values (BSRN, ND, Cp, C9, 81-day centered averages, observed/adjusted flux conversions), and generates `SW-All.txt` and `SW-All.csv`.
2. **A Command Line Interface (CLI)** for automated compiles.
3. **A Desktop GUI** (Tkinter-based) to run the compiler, select output directories, search/filter compiled data, and visualize geomagnetic/solar trends.

---

## Proposed Changes

### [New Component] Data Engine & Compiler

This component handles the downloading, merging, calculations, and exporting of the data.

#### [NEW] [engine.py](file:///c:/0_Project_gravity/spaceweather%20data/spaceweather/engine.py)
* Contains functions to download and cache files locally.
* Implements parsing logic for:
  - GFZ Potsdam: `Kp_ap_Ap_SN_F107_since_1932.txt` and `Kp_ap_Ap_SN_F107_nowcast.txt`
  - SIDC Brussels: Sunspot number data (`SN_d_tot_V2.0.txt` and `EISN_current.txt`)
  - Penticton: Solar flux tables (`F107_1947_1996.txt`, `F107_1996_2007.txt`, `fluxtable.txt`)
  - NOAA SWPC: 3-hourly Kp index JSON forecast and 45-day Ap/F10.7 forecast JSON
  - NASA: Monthly predictions for Sunspots and F10.7 (with automatic fallback to the latest available month if the current month is not published yet).
* Implements mathematical and physical calculations:
  - **Bartels Rotation Number (BSRN)** and **Day within cycle (ND)** from date.
  - **Kp to ap** and **ap to Kp** conversion and linear interpolation.
  - **sum(ap) to Cp** classification mapping.
  - **Cp to C9** single-digit index mapping.
  - **81-day centered** and **81-day backward** moving averages for solar flux.
  - **Earth-Sun distance adjustment** using J2000 orbital mechanics to scale between observed and adjusted solar flux.
* Merges the time-series data chronologically:
  - **Observed Data**: From 1957-10-01 to yesterday.
  - **Daily Predicted Data**: Next 45 days (Day 1-3 using 3-hourly SWPC predictions, Day 4-45 using daily forecast, filled using NASA monthly predictions).
  - **Monthly Predicted Data**: Next ~18 years (using NASA monthly forecast, output for the first day of each month).

---

### [New Component] User Interfaces

This component exposes the functionality via a CLI and a beautiful desktop GUI.

#### [NEW] [cli.py](file:///c:/0_Project_gravity/spaceweather%20data/spaceweather/cli.py)
* Standard Python CLI parsing (`argparse`).
* Commands:
  - `--compile`: Run compilation and save output.
  - `--output`: Define path and format (TXT or CSV).
  - `--verbose`: Print status logs during downloading/processing.

#### [NEW] [gui.py](file:///c:/0_Project_gravity/spaceweather%20data/spaceweather/gui.py)
* Native Tkinter application styled with modern, clean, dark-themed aesthetics.
* Features:
  - **Compiler Panel**: One-click download & compile button with progress indicators and status logs.
  - **Data Viewer**: A grid/table view to inspect the compiled database.
  - **Search & Filter**: Search by date range, filter by high geomagnetic activity (e.g. Kp >= 50).
  - **Trend Visualization**: A lightweight matplotlib plot (with standard library canvas fallback) showing solar flux (F10.7) and geomagnetic index (Ap) trends over the last 30 days and predictions.

#### [NEW] [main.py](file:///c:/0_Project_gravity/spaceweather%20data/main.py)
* Main entry point of the app.
* Runs the GUI by default; runs the CLI if command-line arguments are provided.

#### [NEW] [requirements.txt](file:///c:/0_Project_gravity/spaceweather%20data/requirements.txt)
* Declares standard dependencies: `requests`, `numpy`, `pandas`, `matplotlib`.
* Note: The code will be designed to work even if only standard library dependencies are present (using `urllib` instead of `requests` and simple canvas elements instead of `matplotlib` if necessary), ensuring maximum portability.

---

## Verification Plan

### Automated Verification
We will run a script to compile the file and compare it against the official `SW-All.txt` from Celestrak for consistency:
- Check that the first observed row (1957-10-01) matches exactly.
- Check that a row from 2000-01-01 matches exactly.
- Check that all columns line up perfectly according to the legacy format description.

### Manual Verification
- Launch the GUI and verify that the layout looks clean, modern, and dark-themed.
- Test downloading and compiling the dataset.
- Verify that the generated `SW-All.txt` file is created successfully.
- Search for a specific date (e.g. today's date) and check that predicted data is rendered.
