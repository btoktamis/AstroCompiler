import os
import re
import math
import json
from datetime import datetime, timezone, timedelta
import urllib.request

# Global constants for conversions
# Standard Kp to ap table (Bartels)
# Kp is represented as 10 * float (e.g. 3.333 -> 33, 3.667 -> 37, 4.0 -> 40)
KP_TO_AP_MAP = {
    0: 0, 3: 2, 7: 3, 10: 4, 13: 5, 17: 6, 20: 7, 23: 9, 27: 12, 30: 15,
    33: 18, 37: 22, 40: 27, 43: 32, 47: 39, 50: 48, 53: 56, 57: 67,
    60: 80, 63: 94, 70: 111, 73: 132, 77: 154, 80: 179, 83: 207,
    87: 236, 90: 300, 93: 400
}

# Standard ap to Kp map derived from historical data (1-to-1 mapping)
AP_TO_KP_MAP = {
    0: 0, 2: 3, 3: 7, 4: 10, 5: 13, 6: 17, 7: 20, 9: 23, 12: 27, 15: 30,
    18: 33, 22: 37, 27: 40, 32: 43, 39: 47, 48: 50, 56: 53, 67: 57,
    80: 60, 94: 63, 111: 67, 132: 70, 154: 73, 179: 77, 207: 80,
    236: 83, 300: 87, 400: 90
}

# Sorted lists for interpolation
XP_AP = sorted(AP_TO_KP_MAP.keys())
FP_KP = [AP_TO_KP_MAP[x] for x in XP_AP]

def ap_to_kp(ap):
    """
    Interpolates Kp from ap using standard table values.
    Returns Kp multiplied by 10 (e.g. 2.33 -> 23).
    """
    if ap in AP_TO_KP_MAP:
        return AP_TO_KP_MAP[ap]
    # Linear interpolation fallback
    if ap <= 0: return 0
    if ap >= 400: return 90
    # Find lower and upper bounds
    for i in range(len(XP_AP) - 1):
        if XP_AP[i] <= ap <= XP_AP[i+1]:
            x0, x1 = XP_AP[i], XP_AP[i+1]
            y0, y1 = FP_KP[i], FP_KP[i+1]
            y = y0 + (y1 - y0) * (ap - x0) / (x1 - x0)
            return int(round(y))
    return 0

def ap_sum_to_cp(ap_sum):
    """
    Converts the daily sum of ap indices to the Cp character figure.
    """
    if ap_sum <= 22: return 0.0
    if ap_sum <= 34: return 0.1
    if ap_sum <= 44: return 0.2
    if ap_sum <= 55: return 0.3
    if ap_sum <= 66: return 0.4
    if ap_sum <= 78: return 0.5
    if ap_sum <= 90: return 0.6
    if ap_sum <= 104: return 0.7
    if ap_sum <= 120: return 0.8
    if ap_sum <= 139: return 0.9
    if ap_sum <= 164: return 1.0
    if ap_sum <= 190: return 1.1
    if ap_sum <= 228: return 1.2
    if ap_sum <= 273: return 1.3
    if ap_sum <= 320: return 1.4
    if ap_sum <= 379: return 1.5
    if ap_sum <= 453: return 1.6
    if ap_sum <= 561: return 1.7
    if ap_sum <= 729: return 1.8
    if ap_sum <= 1119: return 1.9
    if ap_sum <= 1399: return 2.0
    if ap_sum <= 1699: return 2.1
    if ap_sum <= 1999: return 2.2
    if ap_sum <= 2399: return 2.3
    if ap_sum <= 3199: return 2.4
    return 2.5

def cp_to_c9(cp):
    """
    Converts the daily Cp character figure to the single-digit C9 index.
    """
    if cp <= 0.1: return 0
    if cp <= 0.3: return 1
    if cp <= 0.5: return 2
    if cp <= 0.7: return 3
    if cp <= 0.9: return 4
    if cp <= 1.1: return 5
    if cp <= 1.4: return 6
    if cp <= 1.8: return 7
    if cp <= 1.9: return 8
    return 9

def get_bartels_rotation(dt):
    """
    Calculates the Bartels Solar Rotation Number (BSRN) and Day within BSR (ND)
    for a given datetime object. The cycle started on 1832 Feb 8.
    """
    # Start of Bartels Cycle: 1832-02-08
    start_date = datetime(1832, 2, 8, tzinfo=timezone.utc)
    delta_days = (dt.replace(hour=12, minute=0, second=0) - start_date).days
    bsrn = 1 + delta_days // 27
    nd = 1 + delta_days % 27
    return bsrn, nd

def get_earth_sun_distance(dt):
    """
    Calculates the Earth-Sun distance in AU using J2000 orbital mechanics.
    Used for adjusting solar flux between observed and 1 AU values.
    """
    # J2000 Epoch: 2000-01-01 12:00:00 UTC
    j2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    delta_days = (dt - j2000).total_seconds() / 86400.0
    
    # Mean anomaly in radians
    g = math.radians(357.529 + 0.98560028 * delta_days)
    
    # Distance in AU
    r = 1.00014 - 0.01671 * math.cos(g) - 0.00014 * math.cos(2 * g)
    return r

class SpaceWeatherCompiler:
    def __init__(self, cache_dir="./cache", log_callback=None):
        self.cache_dir = cache_dir
        self.log_callback = log_callback
        os.makedirs(cache_dir, exist_ok=True)

    def log(self, msg):
        print(msg)
        if self.log_callback:
            self.log_callback(msg)

    def download_file(self, url, filename):
        """
        Downloads a URL to the cache folder and returns its text content.
        """
        filepath = os.path.join(self.cache_dir, filename)
        self.log(f"Fetching: {url}")
        try:
            import ssl
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
                content = response.read().decode('utf-8')
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return content
        except Exception as e:
            self.log(f"Failed downloading {url}: {e}")
            if os.path.exists(filepath):
                self.log(f"Using cached version of {filename}")
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read()
            raise e

    def fetch_nasa_predictions(self):
        """
        Attempts to download the latest NASA SSN and F10.7 prediction files.
        Tries the current month, and falls back to previous months if they return 404.
        """
        now = datetime.now(timezone.utc)
        months_short = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        
        for i in range(12):
            check_date = now - timedelta(days=30 * i)
            year = check_date.year
            month_num = f"{check_date.month:02d}"
            month_name = months_short[check_date.month - 1]
            
            ssn_url = f"https://www.nasa.gov/wp-content/uploads/{year}/{month_num}/{month_name}{year}ssn-prd.txt"
            f107_url = f"https://www.nasa.gov/wp-content/uploads/{year}/{month_num}/{month_name}{year}f10-prd.txt"
            
            try:
                ssn_content = self.download_file(ssn_url, f"ssn_prd_{month_name}{year}.txt")
                f107_content = self.download_file(f107_url, f"f10_prd_{month_name}{year}.txt")
                self.log(f"Successfully loaded NASA predictions for {month_name.upper()} {year}")
                return ssn_content, f107_content
            except Exception:
                # Try previous month
                continue
                
        raise RuntimeError("Could not find any available NASA monthly prediction files in the last 12 months.")

    def parse_gfz_since_1932(self, content):
        """
        Parses the Niemegk historical/nowcast data file.
        Returns a list of dicts.
        """
        records = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 28:
                continue
            
            try:
                # Format columns:
                # 0: YYYY, 1: MM, 2: DD
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                
                # BSRN and ND
                bsrn = int(parts[5])
                nd = int(parts[6])
                
                # Kp1..Kp8 (float values in GFZ Niemegk, e.g. 3.333)
                # Convert to Celestrak integers (multiplied by 10 and rounded)
                kp_vals = []
                for val_str in parts[7:15]:
                    val = float(val_str)
                    if val < 0:
                        kp_vals.append(-1)
                    else:
                        kp_vals.append(int(round(val * 10)))
                
                # ap1..ap8
                ap_vals = [int(p) for p in parts[15:23]]
                
                # Ap, SN (Sunspot Number)
                ap_avg = int(parts[23])
                isn = int(parts[24])
                
                # F10.7Obs and F10.7Adj
                f107_obs = float(parts[25])
                f107_adj = float(parts[26])
                
                records.append({
                    "date": f"{year}-{month:02d}-{day:02d}",
                    "year": year,
                    "month": month,
                    "day": day,
                    "bsrn": bsrn,
                    "nd": nd,
                    "kp_vals": kp_vals,
                    "ap_vals": ap_vals,
                    "ap_avg": ap_avg,
                    "isn": isn,
                    "f107_obs": f107_obs,
                    "f107_adj": f107_adj,
                    "source": "GFZ"
                })
            except Exception as e:
                # Skip malformed lines
                continue
        return records

    def parse_noaa_45day(self, content):
        """
        Parses the NOAA 45-day forecast JSON.
        Returns a dictionary keyed by date string -> {ap, f107}.
        """
        data_dict = {}
        try:
            parsed = json.loads(content)
            for item in parsed.get("data", []):
                # Format: {"time": "2026-06-15T00:00:00Z", "metric": "ap"/"f107", "value": 8}
                time_str = item["time"][:10]
                metric = item["metric"]
                val = int(item["value"])
                
                if time_str not in data_dict:
                    data_dict[time_str] = {}
                data_dict[time_str][metric] = val
        except Exception as e:
            self.log(f"Error parsing NOAA 45-day JSON: {e}")
        return data_dict

    def parse_noaa_3hr(self, content):
        """
        Parses the NOAA 3-hourly Kp JSON forecast.
        Returns a dictionary keyed by date string -> list of 8 Kp values.
        """
        forecast = {}
        try:
            parsed = json.loads(content)
            # Format: [{"time_tag":"2026-06-15T06:00:00","kp":2.67,"observed":"estimated",...}]
            for item in parsed:
                time_str = item["time_tag"]
                dt = datetime.strptime(time_str[:13], "%Y-%m-%dT%H")
                date_key = dt.strftime("%Y-%m-%d")
                kp_val = float(item["kp"])
                # Map hour to 3-hourly index (0-7)
                idx = dt.hour // 3
                
                if date_key not in forecast:
                    forecast[date_key] = [-1.0] * 8
                forecast[date_key][idx] = kp_val
        except Exception as e:
            self.log(f"Error parsing NOAA 3-hour JSON: {e}")
        return forecast

    def parse_nasa_table(self, content):
        """
        Parses monthly predictions from NASA text files.
        Returns a dictionary keyed by YYYY-MM -> value (50th percentile).
        """
        predictions = {}
        # Parse month names mapping
        months_map = {
            "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
            "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
        }
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("TABLE") or line.startswith("TIME") or line.startswith("PERCENTILE"):
                continue
            
            parts = line.split()
            if len(parts) < 3:
                continue
            
            # Pattern check: 2026.4170   JUN   120.9      93.5 ...
            # parts[0] is time fraction, parts[1] is month short name
            m_str = parts[1].upper()
            if m_str in months_map:
                try:
                    time_frac = float(parts[0])
                    year = int(math.floor(time_frac))
                    month = months_map[m_str]
                    # The 50th percentile is column 3 (index 3)
                    val = float(parts[3])
                    predictions[f"{year}-{month:02d}"] = val
                except ValueError:
                    continue
        return predictions

    def compile(self):
        """
        Runs the full compilation process.
        Returns a dictionary with observed, daily predicted, and monthly predicted points.
        """
        self.log("Starting space weather compilation...")
        
        # 1. Fetch all raw data feeds
        gfz_hist_content = self.download_file(
            "https://www-app3.gfz-potsdam.de/kp_index/Kp_ap_Ap_SN_F107_since_1932.txt",
            "gfz_since_1932.txt"
        )
        # We also attempt to get the nowcast file
        try:
            gfz_nowcast_content = self.download_file(
                "https://www-app3.gfz-potsdam.de/kp_index/Kp_ap_Ap_SN_F107_nowcast.txt",
                "gfz_nowcast.txt"
            )
        except Exception:
            gfz_nowcast_content = ""
            
        noaa_45day_content = self.download_file(
            "https://services.swpc.noaa.gov/json/45-day-forecast.json",
            "noaa_45day.json"
        )
        noaa_3hr_content = self.download_file(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json",
            "noaa_3hr.json"
        )
        
        nasa_ssn_content, nasa_f107_content = self.fetch_nasa_predictions()

        # 2. Parse all data feeds
        records = self.parse_gfz_since_1932(gfz_hist_content)
        if gfz_nowcast_content:
            nowcast_records = self.parse_gfz_since_1932(gfz_nowcast_content)
            # Merge nowcast records to override historical records if there is overlap
            gfz_dict = {r["date"]: r for r in records}
            for nr in nowcast_records:
                gfz_dict[nr["date"]] = nr
            records = sorted(gfz_dict.values(), key=lambda x: x["date"])
            
        # Parse forecasts
        noaa_45day = self.parse_noaa_45day(noaa_45day_content)
        noaa_3hr = self.parse_noaa_3hr(noaa_3hr_content)
        nasa_ssn = self.parse_nasa_table(nasa_ssn_content)
        nasa_f107 = self.parse_nasa_table(nasa_f107_content)

        # 3. Filter observed section to start from 1957-10-01
        start_date = "1957-10-01"
        observed_records = [r for r in records if r["date"] >= start_date]
        
        if not observed_records:
            raise RuntimeError("No observed records found starting from 1957-10-01.")

        last_observed_date_str = observed_records[-1]["date"]
        self.log(f"Observed data goes from 1957-10-01 to {last_observed_date_str}")

        # 4. Generate Daily Predictions (next 45 days)
        daily_predicted = []
        last_observed_dt = datetime.strptime(last_observed_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        
        # Build timeline for predictions
        for i in range(1, 46):
            pred_dt = last_observed_dt + timedelta(days=i)
            pred_date_str = pred_dt.strftime("%Y-%m-%d")
            
            bsrn, nd = get_bartels_rotation(pred_dt)
            year, month, day = pred_dt.year, pred_dt.month, pred_dt.day
            
            # Get NOAA forecast values (ap and f10.7)
            # Default to reasonable values if NOAA misses a date
            noaa_vals = noaa_45day.get(pred_date_str, {"ap": 8, "f107": 120})
            ap_avg = noaa_vals.get("ap", 8)
            f107_adj = float(noaa_vals.get("f107", 120))
            
            # Fill 3-hourly Kp and ap
            kp_vals = []
            ap_vals = []
            
            # Check if we have 3-hourly Kp predictions from NOAA (only available for the first ~3 days)
            if pred_date_str in noaa_3hr:
                kp_forecast = noaa_3hr[pred_date_str]
                # Convert floats to Kp (x10) and calculate ap
                for kp_f in kp_forecast:
                    if kp_f < 0:
                        # Fallback to daily average
                        ap_val = ap_avg
                        kp_val = ap_to_kp(ap_val)
                    else:
                        kp_val = int(round(kp_f * 10))
                        # Find closest ap in conversion map
                        ap_val = 0
                        min_diff = 9999
                        for kp_m, ap_m in KP_TO_AP_MAP.items():
                            if abs(kp_m - kp_val) < min_diff:
                                min_diff = abs(kp_m - kp_val)
                                ap_val = ap_m
                    kp_vals.append(kp_val)
                    ap_vals.append(ap_val)
            else:
                # Set all 3-hourly ap to the daily predicted ap
                ap_vals = [ap_avg] * 8
                kp_val = ap_to_kp(ap_avg)
                kp_vals = [kp_val] * 8

            kp_sum = sum(kp_vals)
            ap_sum = sum(ap_vals)
            cp = ap_sum_to_cp(ap_sum)
            c9 = cp_to_c9(cp)
            
            # Fetch NASA monthly predicted ISN for this month
            month_key = f"{year}-{month:02d}"
            isn = int(round(nasa_ssn.get(month_key, 70.0)))
            
            # Calculate observed F10.7 from adjusted using Earth-Sun distance
            r_dist = get_earth_sun_distance(pred_dt)
            f107_obs = f107_adj / (r_dist * r_dist)
            
            daily_predicted.append({
                "date": pred_date_str,
                "year": year,
                "month": month,
                "day": day,
                "bsrn": bsrn,
                "nd": nd,
                "kp_vals": kp_vals,
                "ap_vals": ap_vals,
                "ap_avg": ap_avg,
                "isn": isn,
                "f107_obs": f107_obs,
                "f107_adj": f107_adj,
                "source": "NOAA_PRED"
            })

        # 5. Generate Monthly Predictions (next ~18 years)
        # Starts from the month of the last daily prediction, outputs for the 1st of each month
        monthly_predicted = []
        last_daily_dt = datetime.strptime(daily_predicted[-1]["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        
        # Start at the 1st of the next month
        if last_daily_dt.month == 12:
            start_monthly_year = last_daily_dt.year + 1
            start_monthly_month = 1
        else:
            start_monthly_year = last_daily_dt.year
            start_monthly_month = last_daily_dt.month + 1
            
        current_monthly_dt = datetime(start_monthly_year, start_monthly_month, 1, tzinfo=timezone.utc)
        
        # Fill for approximately 18.5 years (220 months)
        for _ in range(220):
            year, month = current_monthly_dt.year, current_monthly_dt.month
            month_key = f"{year}-{month:02d}"
            
            # Check if predictions are available in NASA tables
            if month_key not in nasa_f107 or month_key not in nasa_ssn:
                # Out of predictions range, stop
                break
                
            bsrn, nd = get_bartels_rotation(current_monthly_dt)
            isn = int(round(nasa_ssn[month_key]))
            f107_adj = float(nasa_f107[month_key])
            
            # Calculate observed F10.7
            r_dist = get_earth_sun_distance(current_monthly_dt)
            f107_obs = f107_adj / (r_dist * r_dist)
            
            monthly_predicted.append({
                "date": current_monthly_dt.strftime("%Y-%m-%d"),
                "year": year,
                "month": month,
                "day": 1,
                "bsrn": bsrn,
                "nd": nd,
                "isn": isn,
                "f107_obs": f107_obs,
                "f107_adj": f107_adj,
                "source": "NASA_PRED"
            })
            
            # Advance to 1st of next month
            if month == 12:
                current_monthly_dt = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                current_monthly_dt = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        # 6. Moving Averages Calculation (81-day centered and backward averages)
        # To handle boundaries correctly, we build a continuous list of F10.7 values
        # combining Observed and Daily Predicted (and dummy future values if needed)
        timeline = []
        for r in observed_records:
            timeline.append({"obs": r["f107_obs"], "adj": r["f107_adj"], "type": "OBS"})
        for r in daily_predicted:
            timeline.append({"obs": r["f107_obs"], "adj": r["f107_adj"], "type": "DAILY"})
            
        # Append some monthly-interpolated values to the timeline to allow calculation
        # of centered average for the last 40 days of daily predictions
        # We fill by repeating or interpolating the monthly predictions
        monthly_map = {m["date"][:7]: m for m in monthly_predicted}
        last_dt = datetime.strptime(daily_predicted[-1]["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        for j in range(1, 100):
            fut_dt = last_dt + timedelta(days=j)
            f_key = fut_dt.strftime("%Y-%m")
            if f_key in monthly_map:
                m_val = monthly_map[f_key]
                timeline.append({"obs": m_val["f107_obs"], "adj": m_val["f107_adj"], "type": "MONTH_FILL"})
            else:
                # Use last available prediction
                timeline.append({"obs": daily_predicted[-1]["f107_obs"], "adj": daily_predicted[-1]["f107_adj"], "type": "MONTH_FILL"})

        # Linearly interpolate missing observed F10.7 values (-1.0)
        # Celestrak performs linear interpolation of missing values (Q=4)
        n = len(observed_records)
        
        # Function to interpolate list
        def interpolate_series(series):
            series = series.copy()
            # Find indices of valid values
            valid_indices = [i for i, x in enumerate(series) if x > 0]
            if not valid_indices:
                return series
            # Interpolate in between
            for k in range(len(valid_indices) - 1):
                idx0, idx1 = valid_indices[k], valid_indices[k+1]
                if idx1 - idx0 > 1:
                    y0, y1 = series[idx0], series[idx1]
                    for idx in range(idx0 + 1, idx1):
                        series[idx] = y0 + (y1 - y0) * (idx - idx0) / (idx1 - idx0)
            # Extrapolate boundaries
            first_idx = valid_indices[0]
            for idx in range(first_idx):
                series[idx] = series[first_idx]
            last_idx = valid_indices[-1]
            for idx in range(last_idx + 1, len(series)):
                series[idx] = series[last_idx]
            return series

        obs_series = [t["obs"] for t in timeline]
        adj_series = [t["adj"] for t in timeline]
        
        # We only interpolate the observed section (first n elements)
        obs_series_interp = interpolate_series(obs_series[:n]) + obs_series[n:]
        adj_series_interp = interpolate_series(adj_series[:n]) + adj_series[n:]
        
        # Update timeline
        for i in range(len(timeline)):
            timeline[i]["obs"] = obs_series_interp[i]
            timeline[i]["adj"] = adj_series_interp[i]

        # Calculate moving averages
        # Center81: average of 81 days centered on day i (i-40 to i+40)
        # Last81: average of 81 days up to day i (i-80 to i)
        for i in range(len(timeline)):
            # Centered 81-day average
            if i >= 40 and i < len(timeline) - 40:
                timeline[i]["obs_ctr"] = sum(t["obs"] for t in timeline[i-40:i+41]) / 81.0
                timeline[i]["adj_ctr"] = sum(t["adj"] for t in timeline[i-40:i+41]) / 81.0
            else:
                # Boundary fallbacks
                timeline[i]["obs_ctr"] = timeline[i]["obs"]
                timeline[i]["adj_ctr"] = timeline[i]["adj"]
                
            # Last 81-day average
            if i >= 80:
                timeline[i]["obs_last"] = sum(t["obs"] for t in timeline[i-80:i+1]) / 81.0
                timeline[i]["adj_last"] = sum(t["adj"] for t in timeline[i-80:i+1]) / 81.0
            else:
                timeline[i]["obs_last"] = timeline[i]["obs"]
                timeline[i]["adj_last"] = timeline[i]["adj"]

        # Write averages back to observed and daily predicted records
        for idx, r in enumerate(observed_records):
            # Check if value was interpolated
            orig_val = records[idx + (len(records) - len(observed_records))]["f107_obs"]
            # Q flag: 0=no adjustment, 4=Celestrak interpolated, 1-3=adjusted/approximated/no obs
            if orig_val <= 0:
                r["q_flag"] = 4  # Interpolated
            else:
                r["q_flag"] = 0  # Observed
                
            r["f107_obs"] = timeline[idx]["obs"]
            r["f107_adj"] = timeline[idx]["adj"]
            r["f107_obs_ctr"] = timeline[idx]["obs_ctr"]
            r["f107_obs_last"] = timeline[idx]["obs_last"]
            r["f107_adj_ctr"] = timeline[idx]["adj_ctr"]
            r["f107_adj_last"] = timeline[idx]["adj_last"]

        for idx, r in enumerate(daily_predicted):
            t_idx = n + idx
            r["q_flag"] = 2  # Predicted (value 2 represents approximation/prediction in legacy)
            r["f107_obs"] = timeline[t_idx]["obs"]
            r["f107_adj"] = timeline[t_idx]["adj"]
            r["f107_obs_ctr"] = timeline[t_idx]["obs_ctr"]
            r["f107_obs_last"] = timeline[t_idx]["obs_last"]
            r["f107_adj_ctr"] = timeline[t_idx]["adj_ctr"]
            r["f107_adj_last"] = timeline[t_idx]["adj_last"]

        # 7. For Monthly Predictions, calculate the moving averages
        # Since these are monthly values, Celestrak sets centers/lasts to adjusted values or leaves them as predicted.
        # Let's inspect the monthly records in SW-All.txt:
        # Cp, C9 are blank, Kp/ap is blank.
        # Adjusted and Observed Center81 / Last81 are simply filled with F10.7_ADJ and F10.7_OBS respectively.
        for r in monthly_predicted:
            r["f107_obs_ctr"] = r["f107_obs"]
            r["f107_obs_last"] = r["f107_obs"]
            r["f107_adj_ctr"] = r["f107_adj"]
            r["f107_adj_last"] = r["f107_adj"]
            r["q_flag"] = 2

        self.log(f"Compilation finished. Observed={len(observed_records)}, Daily={len(daily_predicted)}, Monthly={len(monthly_predicted)}")
        
        return {
            "observed": observed_records,
            "daily": daily_predicted,
            "monthly": monthly_predicted
        }

    def write_to_legacy_txt(self, data, filepath):
        """
        Writes the compiled data structures into the official SW-All.txt legacy fixed-width format.
        """
        # Header template
        updated_str = datetime.now(timezone.utc).strftime("%Y %b %d %H:%M:%S UTC")
        
        header_lines = [
            "DATATYPE CssiSpaceWeather",
            "VERSION 1.2",
            f"UPDATED {updated_str}",
            "",
            f"NUM_OBSERVED_POINTS {len(data['observed'])}",
            "BEGIN OBSERVED"
        ]
        
        # Observed rows formatting
        # yyyy mm dd nnnn nn nn nn nn nn nn nn nn nn nnn nnn nnn nnn nnn nnn nnn nnn nnn nnn n.n n nnn nnn.n n nnn.n nnn.n nnn.n nnn.n nnn.n
        # Formats:
        # yyyy: I4, mm: I3, dd: I3 (blank separation, total 10 chars for date)
        # BSRN: I5 (columns 12-15 is BSRN, ND is I3 columns 17-18)
        # Kp1..Kp8: 8I3
        # Sum: I4
        # ap1..ap8: 8I4
        # Avg: I4
        # Cp: F4.1
        # C9: I2
        # ISN: I4
        # F10.7_ADJ: F6.1
        # Q: I2
        # Ctr81_adj: F6.1, Lst81_adj: F6.1
        # F10.7_OBS: F6.1
        # Ctr81_obs: F6.1, Lst81_obs: F6.1
        
        for r in data['observed']:
            # Calculate Cp, C9
            ap_sum = sum(r['ap_vals'])
            cp = ap_sum_to_cp(ap_sum)
            c9 = cp_to_c9(cp)
            
            # Kp formatted values: if missing, write blank
            kp_str = "".join(f"{v:3d}" if v >= 0 else "   " for v in r['kp_vals'])
            kp_sum_str = f"{sum(r['kp_vals']):3d}" if min(r['kp_vals']) >= 0 else "   "
            
            # ap formatted values
            ap_str = "".join(f"{v:4d}" for v in r['ap_vals'])
            
            row = (
                f"{r['year']:4d} {r['month']:02d} {r['day']:02d}"  # 001-010
                f"{r['bsrn']:5d}"                                  # 011-015
                f"{r['nd']:3d}"                                    # 016-018
                f"{kp_str}"                                        # 019-042
                f"{kp_sum_str}"                                    # 043-046
                f"{ap_str}"                                        # 047-078
                f"{r['ap_avg']:4d}"                                # 079-082
                f"{cp:4.1f}"                                       # 083-086
                f"{c9:2d}"                                         # 087-088
                f"{r['isn']:4d}"                                   # 089-092
                f"{r['f107_adj']:6.1f}"                            # 093-098
                f"{r['q_flag']:2d}"                                # 099-100
                f"{r['f107_adj_ctr']:6.1f}"                        # 101-106
                f"{r['f107_adj_last']:6.1f}"                        # 107-112
                f"{r['f107_obs']:6.1f}"                            # 113-118
                f"{r['f107_obs_ctr']:6.1f}"                        # 119-124
                f"{r['f107_obs_last']:6.1f}"                        # 125-130
            )
            header_lines.append(row)
            
        header_lines.append("END OBSERVED")
        header_lines.append("")
        header_lines.append(f"NUM_DAILY_PREDICTED_POINTS {len(data['daily'])}")
        header_lines.append("BEGIN DAILY_PREDICTED")
        
        for r in data['daily']:
            ap_sum = sum(r['ap_vals'])
            cp = ap_sum_to_cp(ap_sum)
            c9 = cp_to_c9(cp)
            
            kp_str = "".join(f"{v:3d}" for v in r['kp_vals'])
            kp_sum_str = f"{sum(r['kp_vals']):3d}"
            ap_str = "".join(f"{v:4d}" for v in r['ap_vals'])
            
            row = (
                f"{r['year']:4d} {r['month']:02d} {r['day']:02d}"
                f"{r['bsrn']:5d}"
                f"{r['nd']:3d}"
                f"{kp_str}"
                f"{kp_sum_str}"
                f"{ap_str}"
                f"{r['ap_avg']:4d}"
                f"{cp:4.1f}"
                f"{c9:2d}"
                f"{r['isn']:4d}"
                f"{r['f107_adj']:6.1f}"
                f"  "                                             # Q is blank in predictions
                f"{r['f107_adj_ctr']:6.1f}"
                f"{r['f107_adj_last']:6.1f}"
                f"{r['f107_obs']:6.1f}"
                f"{r['f107_obs_ctr']:6.1f}"
                f"{r['f107_obs_last']:6.1f}"
            )
            header_lines.append(row)
            
        header_lines.append("END DAILY_PREDICTED")
        header_lines.append("")
        header_lines.append(f"NUM_MONTHLY_PREDICTED_POINTS {len(data['monthly'])}")
        header_lines.append("BEGIN MONTHLY_PREDICTED")
        
        for r in data['monthly']:
            # Monthly rows format:
            # yyyy mm dd BSRN ND ISN F10.7_ADJ Ctr81 Lst81 F10.7_OBS Ctr81 Lst81
            # Note: columns for Kp, ap, Cp, C9 are left entirely blank!
            # Format requires the fields to align.
            row = (
                f"{r['year']:4d} {r['month']:02d} {r['day']:02d}"  # 001-010
                f"{r['bsrn']:5d}"                                  # 011-015
                f"{r['nd']:3d}"                                    # 016-018
                f"{' ' * 70}"                                      # 019-088 (66 characters blank for Kp, ap, Cp, C9)
                f"{r['isn']:4d}"                                   # 089-092
                f"{r['f107_adj']:6.1f}"                            # 093-098
                f"  "                                              # 099-100 (Q is blank)
                f"{r['f107_adj_ctr']:6.1f}"                        # 101-106
                f"{r['f107_adj_last']:6.1f}"                        # 107-112
                f"{r['f107_obs']:6.1f}"                            # 113-118
                f"{r['f107_obs_ctr']:6.1f}"                        # 119-124
                f"{r['f107_obs_last']:6.1f}"                        # 125-130
            )
            header_lines.append(row)
            
        header_lines.append("END MONTHLY_PREDICTED")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(header_lines) + "\n")
            
        self.log(f"Legacy TXT file saved: {filepath}")

    def write_to_csv(self, data, filepath):
        """
        Writes the compiled data structures into CSV format.
        """
        headers = [
            "DATE", "BSRN", "ND", "KP1", "KP2", "KP3", "KP4", "KP5", "KP6", "KP7", "KP8", "KP_SUM",
            "AP1", "AP2", "AP3", "AP4", "AP5", "AP6", "AP7", "AP8", "AP_AVG", "CP", "C9", "ISN",
            "F10.7_OBS", "F10.7_ADJ", "F10.7_DATA_TYPE", "F10.7_OBS_CENTER81", "F10.7_OBS_LAST81",
            "F10.7_ADJ_CENTER81", "F10.7_ADJ_LAST81"
        ]
        
        csv_rows = [",".join(headers)]
        
        # 1. Observed
        for r in data['observed']:
            ap_sum = sum(r['ap_vals'])
            cp = ap_sum_to_cp(ap_sum)
            c9 = cp_to_c9(cp)
            
            row = [
                r['date'],
                str(r['bsrn']),
                str(r['nd']),
                *[str(v) if v >= 0 else "" for v in r['kp_vals']],
                str(sum(r['kp_vals'])) if min(r['kp_vals']) >= 0 else "",
                *[str(v) for v in r['ap_vals']],
                str(r['ap_avg']),
                f"{cp:.1f}",
                str(c9),
                str(r['isn']),
                f"{r['f107_obs']:.1f}",
                f"{r['f107_adj']:.1f}",
                "OBS",
                f"{r['f107_obs_ctr']:.1f}",
                f"{r['f107_obs_last']:.1f}",
                f"{r['f107_adj_ctr']:.1f}",
                f"{r['f107_adj_last']:.1f}"
            ]
            csv_rows.append(",".join(row))
            
        # 2. Daily predicted
        for r in data['daily']:
            ap_sum = sum(r['ap_vals'])
            cp = ap_sum_to_cp(ap_sum)
            c9 = cp_to_c9(cp)
            
            row = [
                r['date'],
                str(r['bsrn']),
                str(r['nd']),
                *[str(v) for v in r['kp_vals']],
                str(sum(r['kp_vals'])),
                *[str(v) for v in r['ap_vals']],
                str(r['ap_avg']),
                f"{cp:.1f}",
                str(c9),
                str(r['isn']),
                f"{r['f107_obs']:.1f}",
                f"{r['f107_adj']:.1f}",
                "PRD",
                f"{r['f107_obs_ctr']:.1f}",
                f"{r['f107_obs_last']:.1f}",
                f"{r['f107_adj_ctr']:.1f}",
                f"{r['f107_adj_last']:.1f}"
            ]
            csv_rows.append(",".join(row))
            
        # 3. Monthly predicted
        for r in data['monthly']:
            # Set unpredicted values to empty
            row = [
                r['date'],
                str(r['bsrn']),
                str(r['nd']),
                "", "", "", "", "", "", "", "", "",  # Kp1..Kp8, Sum
                "", "", "", "", "", "", "", "", "",  # ap1..ap8, Avg
                "", "",                              # Cp, C9
                str(r['isn']),
                f"{r['f107_obs']:.1f}",
                f"{r['f107_adj']:.1f}",
                "PRM",
                f"{r['f107_obs_ctr']:.1f}",
                f"{r['f107_obs_last']:.1f}",
                f"{r['f107_adj_ctr']:.1f}",
                f"{r['f107_adj_last']:.1f}"
            ]
            csv_rows.append(",".join(row))

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(csv_rows) + "\n")
            
        self.log(f"CSV file saved: {filepath}")

    def verify_with_celestrak(self, generated_filepath):
        """
        Downloads Celestrak's SW-All.txt and compares it to our generated file.
        Outputs comparison metrics (match rate, discrepancy list).
        """
        self.log("Starting compatibility check with CelesTrak...")
        
        celestrak_url = "https://celestrak.org/SpaceData/SW-All.txt"
        celestrak_content = self.download_file(celestrak_url, "celestrak_sw_all_target.txt")
        
        # Parse official file
        official_obs = {}
        official_daily = {}
        official_monthly = {}
        
        def parse_legacy_content(content):
            obs, daily, monthly = {}, {}, {}
            current_section = None
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line == "BEGIN OBSERVED":
                    current_section = "OBS"
                    continue
                elif line == "END OBSERVED":
                    current_section = None
                    continue
                elif line == "BEGIN DAILY_PREDICTED":
                    current_section = "DAILY"
                    continue
                elif line == "END DAILY_PREDICTED":
                    current_section = None
                    continue
                elif line == "BEGIN MONTHLY_PREDICTED":
                    current_section = "MONTHLY"
                    continue
                elif line == "END MONTHLY_PREDICTED":
                    current_section = None
                    continue
                
                if current_section:
                    parts = line.split()
                    if len(parts) >= 5:
                        date_key = f"{parts[0]}-{parts[1]}-{parts[2]}"
                        # We store the entire raw line to compare character-by-character
                        if current_section == "OBS":
                            obs[date_key] = line
                        elif current_section == "DAILY":
                            daily[date_key] = line
                        elif current_section == "MONTHLY":
                            monthly[date_key] = line
            return obs, daily, monthly

        off_obs, off_daily, off_monthly = parse_legacy_content(celestrak_content)
        
        with open(generated_filepath, "r", encoding="utf-8") as f:
            gen_content = f.read()
            
        gen_obs, gen_daily, gen_monthly = parse_legacy_content(gen_content)
        
        self.log(f"Official file points: OBS={len(off_obs)}, DAILY={len(off_daily)}, MONTHLY={len(off_monthly)}")
        self.log(f"Generated file points: OBS={len(gen_obs)}, DAILY={len(gen_daily)}, MONTHLY={len(gen_monthly)}")
        
        # Comparison logic
        discrepancies = []
        matches = 0
        total_checked = 0
        
        # We check the overlap
        for date_key in sorted(off_obs.keys()):
            if date_key in gen_obs:
                total_checked += 1
                off_line = off_obs[date_key]
                gen_line = gen_obs[date_key]
                
                # Check for major parameters: Ap_avg, ISN, F10.7_ADJ, F10.7_OBS
                # Indices in line:
                # Avg is 79-82 (0-indexed indices 78:82)
                # ISN is 89-92 (0-indexed indices 88:92)
                # F10.7_ADJ is 93-98 (0-indexed indices 92:98)
                # F10.7_OBS is 113-118 (0-indexed indices 112:118)
                try:
                    off_avg = int(off_line[78:82].strip())
                    gen_avg = int(gen_line[78:82].strip())
                    
                    off_isn = int(off_line[88:92].strip())
                    gen_isn = int(gen_line[88:92].strip())
                    
                    off_adj = float(off_line[92:98].strip())
                    gen_adj = float(gen_line[92:98].strip())
                    
                    off_obs_val = float(off_line[112:118].strip())
                    gen_obs_val = float(gen_line[112:118].strip())
                    
                    # Allow slight floating point differences (e.g. 0.1 due to roundings)
                    diff_avg = abs(off_avg - gen_avg)
                    diff_isn = abs(off_isn - gen_isn)
                    diff_adj = abs(off_adj - gen_adj)
                    diff_obs = abs(off_obs_val - gen_obs_val)
                    
                    if diff_avg <= 1 and diff_isn <= 2 and diff_adj <= 0.2 and diff_obs <= 0.2:
                        matches += 1
                    else:
                        discrepancies.append(
                            f"OBS {date_key}: CelesTrak=(AvgAp:{off_avg}, ISN:{off_isn}, AdjFlux:{off_adj}, ObsFlux:{off_obs_val}) "
                            f"Local=(AvgAp:{gen_avg}, ISN:{gen_isn}, AdjFlux:{gen_adj}, ObsFlux:{gen_obs_val})"
                        )
                except Exception as e:
                    discrepancies.append(f"OBS {date_key}: Parsing error in line comparison: {e}")

        # Check daily predictions
        daily_matches = 0
        daily_total = 0
        for date_key in sorted(off_daily.keys()):
            if date_key in gen_daily:
                daily_total += 1
                off_line = off_daily[date_key]
                gen_line = gen_daily[date_key]
                
                try:
                    off_avg = int(off_line[78:82].strip())
                    gen_avg = int(gen_line[78:82].strip())
                    
                    off_isn = int(off_line[88:92].strip())
                    gen_isn = int(gen_line[88:92].strip())
                    
                    off_adj = float(off_line[92:98].strip())
                    gen_adj = float(gen_line[92:98].strip())
                    
                    if abs(off_avg - gen_avg) <= 1 and abs(off_isn - gen_isn) <= 2 and abs(off_adj - gen_adj) <= 1.0:
                        daily_matches += 1
                    else:
                        discrepancies.append(
                            f"PRED {date_key}: CelesTrak=(AvgAp:{off_avg}, ISN:{off_isn}, AdjFlux:{off_adj}) "
                            f"Local=(AvgAp:{gen_avg}, ISN:{gen_isn}, AdjFlux:{gen_adj})"
                        )
                except Exception as e:
                    pass

        self.log("\n--- VERIFICATION REPORT ---")
        self.log(f"Observed Section Compatibility: {matches} / {total_checked} matched ({matches/total_checked*100:.2f}%)")
        if daily_total > 0:
            self.log(f"Daily Predictions Compatibility: {daily_matches} / {daily_total} matched ({daily_matches/daily_total*100:.2f}%)")
        
        self.log(f"Total Discrepancies Registered: {len(discrepancies)}")
        if discrepancies:
            self.log("First 10 discrepancies:")
            for d in discrepancies[:10]:
                self.log(f"  - {d}")
        
        return {
            "obs_match_rate": matches / total_checked if total_checked > 0 else 0,
            "pred_match_rate": daily_matches / daily_total if daily_total > 0 else 0,
            "discrepancies": discrepancies
        }
