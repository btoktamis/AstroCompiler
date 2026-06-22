import os
import re
import math
from datetime import datetime, timezone, timedelta
import urllib.request

# NGA Coefficients (legacy block from USNO/NGA)
NGA_COEFFICIENTS_TEXT = """BEGIN NGA_COEFFICIENTS
  58570.00   .120846   .000000   .036936  -.006607  -.093373   .010659365.25
435.00   .353800   .000000   .088580  -.021846   .021361   .003997365.25435.00
  58848.00   .005916  -.000434   .000000   .000000  -.022000   .006000
   .000000   .000000   .012000  -.007000 500.0000 500.0000 365.2500 182.6250
  37 0141 58989  58988 00000    -.433875
END NGA_COEFFICIENTS"""

# Legacy fixed-width format comments template
EOP_COMMENTS_HEADER = """# ----------------------------------------------------------------------------------------------------
#                    EARTH ORIENTATION PARAMETERS (EOP) DATA
# ----------------------------------------------------------------------------------------------------
#
# See http://celestrak.org/SpaceData/EOP-format.php for format details.
#
# ----------------------------------------------------------------------------------------------------
#
# EOP (IERS) 20 C04 TIME SERIES  (old format)
# Description: https://hpiers.obspm.fr/eoppc/eop/eopc04/eopc04.txt
# contact: christian.bizouard@obspm.fr
#
# FORMAT(I4,I3,I3,I6,2F10.6,2F11.7,4F10.6,I4)
# ----------------------------------------------------------------------------------------------------
#   Date    MJD      x         y       UT1-UTC      LOD       dPsi    dEpsilon     dX        dY    DAT
# (0h UTC)           "         "          s          s          "        "          "         "     s 
# ----------------------------------------------------------------------------------------------------
# y4 mm dd nnnnn +n.nnnnnn +n.nnnnnn +n.nnnnnnn +n.nnnnnnn +n.nnnnnn +n.nnnnnn +n.nnnnnn +n.nnnnnn nnn
# ----------------------------------------------------------------------------------------------------
#"""

def parse_tai_utc(content):
    """
    Parses USNO's tai-utc.dat.
    Format:
     1962 JAN  1 =JD 2437665.5  TAI-UTC=   1.8458580 S + (MJD - 37300.) X 0.001296 S
     1972 JAN  1 =JD 2441317.5  TAI-UTC=  10.0       S + (MJD - 41317.) X 0.0      S
    """
    records = []
    pattern = re.compile(
        r"JD\s+(\d+\.\d+)\s+TAI-UTC=\s*([\d\.-]+)\s*S\s*\+\s*\(MJD\s*-\s*([\d\.-]+)\.\)\s*X\s*([\d\.-e]+)\s*S",
        re.IGNORECASE
    )
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        m = pattern.search(line)
        if m:
            try:
                jd = float(m.group(1))
                mjd = int(round(jd - 2400000.5))
                base = float(m.group(2))
                anchor = float(m.group(3))
                drift = float(m.group(4))
                records.append({
                    "mjd": mjd,
                    "base": base,
                    "anchor": anchor,
                    "drift": drift
                })
            except ValueError:
                continue
    records.sort(key=lambda x: x["mjd"])
    return records

def get_dat_for_mjd(mjd, tai_utc_records):
    """
    Retrieves Delta Atomic Time (DAT) for a given MJD from parsed tai-utc.dat.
    """
    active_rec = None
    for rec in tai_utc_records:
        if rec["mjd"] <= mjd:
            active_rec = rec
        else:
            break
    if active_rec is None:
        return 0
    val = active_rec["base"] + (mjd - active_rec["anchor"]) * active_rec["drift"]
    return int(round(val))

def parse_eopc04(content):
    """
    Parses Paris Observatory C04 files (eopc04.1962-now and eopc04.dPsi_dEps.1962-now).
    Returns a dict mapping MJD -> parsed record.
    """
    data = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 13:
            continue
        try:
            # First element must be a year (e.g. 1962)
            year = int(parts[0])
            mjd_val = float(parts[4])
            mjd = int(round(mjd_val))
            
            x = float(parts[5])
            y = float(parts[6])
            ut1_utc = float(parts[7])
            val8 = float(parts[8])
            val9 = float(parts[9])
            lod = float(parts[12])
            
            data[mjd] = {
                "year": year,
                "month": int(parts[1]),
                "day": int(parts[2]),
                "mjd": mjd,
                "x": x,
                "y": y,
                "ut1_utc": ut1_utc,
                "val8": val8,
                "val9": val9,
                "lod": lod
            }
        except ValueError:
            continue
    return data

def parse_bulletin_a(content_2000A, content_1980):
    """
    Parses USNO Bulletin A files:
    finals2000A.all (provides x, y, UT1-UTC, LOD, dX, dY)
    finals.all (provides dPsi, dEpsilon)
    Returns a dict mapping MJD -> parsed record.
    """
    def parse_file(content):
        file_data = {}
        for line in content.splitlines():
            if len(line) < 68:
                continue
            try:
                # Fixed-width format of finals.all/finals2000A.all
                year_str = line[0:2].strip()
                month_str = line[2:4].strip()
                day_str = line[4:6].strip()
                mjd_str = line[7:15].strip()
                if not mjd_str:
                    continue
                mjd = int(round(float(mjd_str)))
                
                # Column 16 is flag for PM values ('I' for observed/rapid, 'P' for predicted)
                flag_pm = line[16]
                if flag_pm not in ('I', 'P'):
                    continue
                
                x_str = line[18:27].strip()
                x = float(x_str) if x_str else 0.0
                
                y_str = line[38:47].strip()
                y = float(y_str) if y_str else 0.0
                
                ut_str = line[58:68].strip()
                ut1_utc = float(ut_str) if ut_str else 0.0
                
                lod_str = ""
                if len(line) >= 86:
                    lod_str = line[79:86].strip()
                lod = (float(lod_str) / 1000.0) if lod_str else 0.0
                
                val1 = 0.0
                val2 = 0.0
                if len(line) >= 125:
                    v1_str = line[97:106].strip()
                    v2_str = line[116:125].strip()
                    val1 = (float(v1_str) / 1000.0) if v1_str else 0.0
                    val2 = (float(v2_str) / 1000.0) if v2_str else 0.0
                
                yy = int(year_str)
                year = 2000 + yy if yy < 50 else 1900 + yy
                
                file_data[mjd] = {
                    "year": year,
                    "month": int(month_str),
                    "day": int(day_str),
                    "mjd": mjd,
                    "x": x,
                    "y": y,
                    "ut1_utc": ut1_utc,
                    "lod": lod,
                    "val1": val1,
                    "val2": val2,
                    "type": "O" if flag_pm == "I" else "P"
                }
            except Exception:
                continue
        return file_data

    dict_2000A = parse_file(content_2000A)
    dict_1980 = parse_file(content_1980)
    
    merged = {}
    for mjd, item in dict_2000A.items():
        item_1980 = dict_1980.get(mjd)
        dpsi = item_1980["val1"] if item_1980 else 0.0
        deps = item_1980["val2"] if item_1980 else 0.0
        
        merged[mjd] = {
            "year": item["year"],
            "month": item["month"],
            "day": item["day"],
            "mjd": mjd,
            "x": item["x"],
            "y": item["y"],
            "ut1_utc": item["ut1_utc"],
            "lod": item["lod"],
            "dpsi": dpsi,
            "deps": deps,
            "dx": item["val1"],
            "dy": item["val2"],
            "type": item["type"]
        }
    return merged


class EOPCompiler:
    def __init__(self, cache_dir="./cache", log_callback=None):
        self.cache_dir = cache_dir
        self.log_callback = log_callback
        os.makedirs(cache_dir, exist_ok=True)

    def log(self, msg):
        print(msg)
        if self.log_callback:
            self.log_callback(msg)

    def download_file(self, url, filename):
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

    def compile(self, offline_mode=True):
        """
        Compiles the EOP dataset by merging IERS observed and USNO predictions.
        If offline_mode is True, it fetches raw primary sources.
        If it fails, or if offline_mode is False, it falls back to downloading CelesTrak's EOP-All.txt.
        """
        if not offline_mode:
            self.log("Compile mode: Celestrak Direct Download. Skipping raw source build...")
            return self.compile_from_celestrak()

        self.log("Starting Earth Orientation Parameters (EOP) compilation from raw IERS/USNO feeds...")
        try:
            # 1. Download raw files
            tai_utc_content = self.download_file("https://maia.usno.navy.mil/ser7/tai-utc.dat", "tai_utc.dat")
            c04_std_content = self.download_file("https://hpiers.obspm.fr/iers/eop/eopc04/eopc04.1962-now", "eopc04_std.txt")
            c04_dpsi_content = self.download_file("https://hpiers.obspm.fr/iers/eop/eopc04/eopc04.dPsi_dEps.1962-now", "eopc04_dpsi.txt")
            finals_2000A_content = self.download_file("https://maia.usno.navy.mil/ser7/finals2000A.all", "finals2000A.all")
            finals_1980_content = self.download_file("https://maia.usno.navy.mil/ser7/finals.all", "finals.all")

            # 2. Parse feeds
            self.log("Parsing raw datasets...")
            tai_utc_records = parse_tai_utc(tai_utc_content)
            
            c04_std = parse_eopc04(c04_std_content)
            c04_dpsi = parse_eopc04(c04_dpsi_content)
            
            bulletin_a = parse_bulletin_a(finals_2000A_content, finals_1980_content)

            # 3. Merge IERS Observed
            self.log("Merging observed parameters...")
            observed_mjd_dict = {}
            for mjd, std_rec in c04_std.items():
                dpsi_rec = c04_dpsi.get(mjd)
                dpsi = dpsi_rec["val8"] if dpsi_rec else 0.0
                deps = dpsi_rec["val9"] if dpsi_rec else 0.0
                
                observed_mjd_dict[mjd] = {
                    "year": std_rec["year"],
                    "month": std_rec["month"],
                    "day": std_rec["day"],
                    "mjd": mjd,
                    "x": std_rec["x"],
                    "y": std_rec["y"],
                    "ut1_utc": std_rec["ut1_utc"],
                    "lod": std_rec["lod"],
                    "dpsi": dpsi,
                    "deps": deps,
                    "dx": std_rec["val8"],
                    "dy": std_rec["val9"]
                }

            max_c04_mjd = max(observed_mjd_dict.keys()) if observed_mjd_dict else 0
            self.log(f"Definitive Observed EOP (IERS C04) ends at MJD {max_c04_mjd}")

            # 4. Partition Bulletin A (Observed vs Predicted)
            bulletin_a_obs = {m: r for m, r in bulletin_a.items() if r["type"] == "O"}
            bulletin_a_pred = {m: r for m, r in bulletin_a.items() if r["type"] == "P"}

            # 5. Build consolidated observed timeline (Starts 1962-01-01, MJD 37665)
            self.log("Constructing consolidated time-series...")
            final_observed = []
            final_predicted = []

            # We determine the last MJD of observed data across C04 and USNO Bulletin A
            all_obs_mjds = sorted(list(observed_mjd_dict.keys()) + list(bulletin_a_obs.keys()))
            if not all_obs_mjds:
                raise ValueError("No observed data found in feeds.")
            
            min_mjd = 37665  # 1962-01-01
            max_obs_mjd = max(all_obs_mjds)

            # Observed loop
            for mjd in range(min_mjd, max_obs_mjd + 1):
                # Pull from C04 first, fallback to USNO observed
                if mjd in observed_mjd_dict:
                    rec = observed_mjd_dict[mjd]
                elif mjd in bulletin_a_obs:
                    rec = bulletin_a_obs[mjd]
                else:
                    # Missing day: skip or interpolate. Since we have continuous series, just skip.
                    continue
                
                dat = get_dat_for_mjd(mjd, tai_utc_records)
                final_observed.append({
                    "year": rec["year"],
                    "month": rec["month"],
                    "day": rec["day"],
                    "mjd": mjd,
                    "x": rec["x"],
                    "y": rec["y"],
                    "ut1_utc": rec["ut1_utc"],
                    "lod": rec["lod"],
                    "dpsi": rec["dpsi"],
                    "deps": rec["deps"],
                    "dx": rec["dx"],
                    "dy": rec["dy"],
                    "dat": dat
                })

            # Predictions loop (next 180 days)
            # Find the consecutive 180 prediction days starting from max_obs_mjd + 1
            pred_count = 0
            curr_pred_mjd = max_obs_mjd + 1
            while pred_count < 185:  # Go up to 180-185 days
                if curr_pred_mjd in bulletin_a_pred:
                    rec = bulletin_a_pred[curr_pred_mjd]
                    dat = get_dat_for_mjd(curr_pred_mjd, tai_utc_records)
                    final_predicted.append({
                        "year": rec["year"],
                        "month": rec["month"],
                        "day": rec["day"],
                        "mjd": curr_pred_mjd,
                        "x": rec["x"],
                        "y": rec["y"],
                        "ut1_utc": rec["ut1_utc"],
                        "lod": rec["lod"],
                        "dpsi": rec["dpsi"],
                        "deps": rec["deps"],
                        "dx": rec["dx"],
                        "dy": rec["dy"],
                        "dat": dat
                    })
                    pred_count += 1
                curr_pred_mjd += 1

            self.log(f"Raw feeds compile successful. Observed={len(final_observed)}, Predicted={len(final_predicted)}")
            return {
                "observed": final_observed,
                "predicted": final_predicted
            }

        except Exception as e:
            self.log(f"Raw feeds compile failed: {e}. Falling back to CelesTrak data...")
            return self.compile_from_celestrak()

    def compile_from_celestrak(self):
        """
        Downloads Celestrak's EOP-All.txt and parses it into EOP Compiler data structures.
        """
        self.log("Downloading EOP-All.txt from CelesTrak...")
        url = "https://celestrak.org/SpaceData/EOP-All.txt"
        content = self.download_file(url, "celestrak_eop_all.txt")
        
        self.log("Parsing Celestrak EOP file...")
        observed = []
        predicted = []
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
            elif line == "BEGIN PREDICTED":
                current_section = "PRED"
                continue
            elif line == "END PREDICTED":
                current_section = None
                continue
                
            if current_section in ("OBS", "PRED"):
                parts = line.split()
                if len(parts) >= 13:
                    try:
                        year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2])
                        mjd = int(parts[3])
                        
                        # Fix columns alignment and parsing
                        x = float(parts[4])
                        y = float(parts[5])
                        ut1_utc = float(parts[6])
                        lod = float(parts[7])
                        dpsi = float(parts[8])
                        deps = float(parts[9])
                        dx = float(parts[10])
                        dy = float(parts[11])
                        dat = int(parts[12])
                        
                        rec = {
                            "year": year,
                            "month": month,
                            "day": day,
                            "mjd": mjd,
                            "x": x,
                            "y": y,
                            "ut1_utc": ut1_utc,
                            "lod": lod,
                            "dpsi": dpsi,
                            "deps": deps,
                            "dx": dx,
                            "dy": dy,
                            "dat": dat
                        }
                        if current_section == "OBS":
                            observed.append(rec)
                        else:
                            predicted.append(rec)
                    except ValueError:
                        continue
        
        self.log(f"Celestrak EOP download successful. Observed={len(observed)}, Predicted={len(predicted)}")
        return {
            "observed": observed,
            "predicted": predicted
        }

    def write_to_legacy_txt(self, data, filepath, legacy_mode=True):
        """
        Writes EOP data to a file in Celestrak legacy text format.
        If legacy_mode is True, it prepends the NGE coefficients block.
        """
        output_lines = []
        
        # 1. Prepend NGE coefficients if legacy mode is active
        if legacy_mode:
            output_lines.append(NGA_COEFFICIENTS_TEXT)
            
        # 2. Version and Updated metadata
        updated_str = datetime.now(timezone.utc).strftime("%Y %b %d %H:%M:%S UTC")
        output_lines.append("VERSION 1.1")
        output_lines.append(f"UPDATED {updated_str}")
        
        # 3. Comments block
        output_lines.append(EOP_COMMENTS_HEADER)
        
        # 4. Observed points
        output_lines.append(f"NUM_OBSERVED_POINTS {len(data['observed'])}")
        output_lines.append("BEGIN OBSERVED")
        for r in data['observed']:
            row = (
                f"{r['year']:4d} {r['month']:02d} {r['day']:02d}"
                f" {r['mjd']:5d}"
                f" {r['x']:9.6f}"
                f" {r['y']:9.6f}"
                f" {r['ut1_utc']:10.7f}"
                f" {r['lod']:10.7f}"
                f" {r['dpsi']:9.6f}"
                f" {r['deps']:9.6f}"
                f" {r['dx']:9.6f}"
                f" {r['dy']:9.6f}"
                f" {r['dat']:3d}"
            )
            output_lines.append(row)
        output_lines.append("END OBSERVED")
        
        # 5. Predicted points
        output_lines.append("")
        output_lines.append(f"NUM_PREDICTED_POINTS {len(data['predicted'])}")
        output_lines.append("BEGIN PREDICTED")
        for r in data['predicted']:
            row = (
                f"{r['year']:4d} {r['month']:02d} {r['day']:02d}"
                f" {r['mjd']:5d}"
                f" {r['x']:9.6f}"
                f" {r['y']:9.6f}"
                f" {r['ut1_utc']:10.7f}"
                f" {r['lod']:10.7f}"
                f" {r['dpsi']:9.6f}"
                f" {r['deps']:9.6f}"
                f" {r['dx']:9.6f}"
                f" {r['dy']:9.6f}"
                f" {r['dat']:3d}"
            )
            output_lines.append(row)
        output_lines.append("END PREDICTED")
        
        # Ensure parent directories exist
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines) + "\n")
            
        self.log(f"Successfully compiled and saved EOP data to: {filepath}")

    def write_to_csv(self, data, filepath):
        """
        Writes EOP data to CSV format.
        """
        headers = ["DATE", "MJD", "X", "Y", "UT1-UTC", "LOD", "DPSI", "DEPS", "DX", "DY", "DAT", "DATA_TYPE"]
        csv_rows = [",".join(headers)]
        
        for r in data['observed']:
            date_str = f"{r['year']:04d}-{r['month']:02d}-{r['day']:02d}"
            row = [
                date_str, str(r['mjd']),
                f"{r['x']:.6f}", f"{r['y']:.6f}", f"{r['ut1_utc']:.7f}", f"{r['lod']:.7f}",
                f"{r['dpsi']:.6f}", f"{r['deps']:.6f}", f"{r['dx']:.6f}", f"{r['dy']:.6f}",
                str(r['dat']), "O"
            ]
            csv_rows.append(",".join(row))
            
        for r in data['predicted']:
            date_str = f"{r['year']:04d}-{r['month']:02d}-{r['day']:02d}"
            row = [
                date_str, str(r['mjd']),
                f"{r['x']:.6f}", f"{r['y']:.6f}", f"{r['ut1_utc']:.7f}", f"{r['lod']:.7f}",
                f"{r['dpsi']:.6f}", f"{r['deps']:.6f}", f"{r['dx']:.6f}", f"{r['dy']:.6f}",
                str(r['dat']), "P"
            ]
            csv_rows.append(",".join(row))
            
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(csv_rows) + "\n")
            
        self.log(f"Successfully saved EOP CSV data to: {filepath}")

    def verify_with_celestrak(self, generated_filepath):
        """
        Compares the generated EOP file with Celestrak's live database.
        Automatically detects if the generated file is legacy (has NGA coefficients block)
        and strips it before parsing.
        """
        self.log("Starting EOP compatibility check with CelesTrak live database...")
        
        celestrak_url = "https://celestrak.org/SpaceData/EOP-All.txt"
        celestrak_content = self.download_file(celestrak_url, "celestrak_eop_all_verify.txt")
        
        # Parse local generated file
        if not os.path.exists(generated_filepath):
            raise FileNotFoundError(f"Generated EOP file not found: {generated_filepath}")
            
        with open(generated_filepath, "r", encoding="utf-8") as f:
            local_content = f.read()
            
        # Helper to parse EOP content
        def parse_eop_sections(text):
            obs_dict = {}
            pred_dict = {}
            
            # Detect legacy format (strip NGA coefficients block)
            if "BEGIN NGA_COEFFICIENTS" in text:
                # Strip everything between BEGIN and END NGA_COEFFICIENTS
                parts = text.split("END NGA_COEFFICIENTS")
                if len(parts) > 1:
                    text = parts[1]
            
            current_section = None
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line == "BEGIN OBSERVED":
                    current_section = "OBS"
                    continue
                elif line == "END OBSERVED":
                    current_section = None
                    continue
                elif line == "BEGIN PREDICTED":
                    current_section = "PRED"
                    continue
                elif line == "END PREDICTED":
                    current_section = None
                    continue
                    
                if current_section in ("OBS", "PRED"):
                    line_parts = line.split()
                    if len(line_parts) >= 13:
                        try:
                            mjd = int(line_parts[3])
                            rec = {
                                "x": float(line_parts[4]),
                                "y": float(line_parts[5]),
                                "ut1_utc": float(line_parts[6]),
                                "lod": float(line_parts[7]),
                                "dpsi": float(line_parts[8]),
                                "deps": float(line_parts[9]),
                                "dx": float(line_parts[10]),
                                "dy": float(line_parts[11]),
                                "dat": int(line_parts[12])
                            }
                            if current_section == "OBS":
                                obs_dict[mjd] = rec
                            else:
                                pred_dict[mjd] = rec
                        except ValueError:
                            continue
            return obs_dict, pred_dict

        self.log("Parsing local and Celestrak files...")
        local_obs, local_pred = parse_eop_sections(local_content)
        ct_obs, ct_pred = parse_eop_sections(celestrak_content)
        
        self.log(f"Live Celestrak Points: OBS={len(ct_obs)}, PRED={len(ct_pred)}")
        self.log(f"Local Generated Points: OBS={len(local_obs)}, PRED={len(local_pred)}")
        
        discrepancies = []
        matches = 0
        total_checked = 0
        
        # Compare Observed
        for mjd in sorted(ct_obs.keys()):
            if mjd in local_obs:
                total_checked += 1
                c = ct_obs[mjd]
                l = local_obs[mjd]
                
                # Check major orbital columns
                diff_x = abs(c["x"] - l["x"])
                diff_y = abs(c["y"] - l["y"])
                diff_ut = abs(c["ut1_utc"] - l["ut1_utc"])
                diff_lod = abs(c["lod"] - l["lod"])
                
                # Tolerances: 0.001 arcsec/seconds
                if diff_x < 0.001 and diff_y < 0.001 and diff_ut < 0.001 and diff_lod < 0.001 and c["dat"] == l["dat"]:
                    matches += 1
                else:
                    discrepancies.append(
                        f"OBS MJD {mjd}: CelesTrak=(x:{c['x']}, y:{c['y']}, UT1:{c['ut1_utc']}, DAT:{c['dat']}) "
                        f"Local=(x:{l['x']}, y:{l['y']}, UT1:{l['ut1_utc']}, DAT:{l['dat']})"
                    )

        # Compare Predicted
        pred_matches = 0
        pred_total = 0
        for mjd in sorted(ct_pred.keys()):
            if mjd in local_pred:
                pred_total += 1
                c = ct_pred[mjd]
                l = local_pred[mjd]
                
                diff_x = abs(c["x"] - l["x"])
                diff_y = abs(c["y"] - l["y"])
                diff_ut = abs(c["ut1_utc"] - l["ut1_utc"])
                
                if diff_x < 0.01 and diff_y < 0.01 and diff_ut < 0.01:
                    pred_matches += 1
                else:
                    discrepancies.append(
                        f"PRED MJD {mjd}: CelesTrak=(x:{c['x']}, y:{c['y']}, UT1:{c['ut1_utc']}) "
                        f"Local=(x:{l['x']}, y:{l['y']}, UT1:{l['ut1_utc']})"
                    )

        obs_rate = matches / total_checked if total_checked > 0 else 0
        pred_rate = pred_matches / pred_total if pred_total > 0 else 0
        
        self.log("\n--- EOP VERIFICATION REPORT ---")
        self.log(f"Observed Section Match: {matches} / {total_checked} ({obs_rate*100:.2f}%)")
        self.log(f"Predicted Section Match: {pred_matches} / {pred_total} ({pred_rate*100:.2f}%)")
        self.log(f"Total Discrepancies: {len(discrepancies)}")
        if discrepancies:
            self.log("First 10 discrepancies:")
            for d in discrepancies[:10]:
                self.log(f"  - {d}")
                
        return {
            "obs_match_rate": obs_rate,
            "pred_match_rate": pred_rate,
            "discrepancies": discrepancies,
            "is_legacy": "BEGIN NGA_COEFFICIENTS" in local_content
        }
