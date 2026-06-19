package eop

import (
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

// EOPRecord represents a single day's Earth Orientation Parameters.
type EOPRecord struct {
	Year   int     `json:"year"`
	Month  int     `json:"month"`
	Day    int     `json:"day"`
	MJD    int     `json:"mjd"`
	X      float64 `json:"x"`
	Y      float64 `json:"y"`
	UT1UTC float64 `json:"ut1_utc"`
	LOD    float64 `json:"lod"`
	DPsi   float64 `json:"dpsi"`
	DEps   float64 `json:"deps"`
	DX     float64 `json:"dx"`
	DY     float64 `json:"dy"`
	DAT    int     `json:"dat"`
	Type   string  `json:"-"` // Internal use: "O" (Observed) or "P" (Predicted)
}

// EOPCompileResult holds observed and predicted datasets.
type EOPCompileResult struct {
	Observed  []EOPRecord `json:"observed"`
	Predicted []EOPRecord `json:"predicted"`
}

// TAIUTCRecord holds atomic time scale leap second configurations.
type TAIUTCRecord struct {
	MJD    int
	Base   float64
	Anchor float64
	Drift  float64
}

// Constants for file writing
const NGALegacyCoefficients = `BEGIN NGA_COEFFICIENTS
  58570.00   .120846   .000000   .036936  -.006607  -.093373   .010659365.25
435.00   .353800   .000000   .088580  -.021846   .021361   .003997365.25435.00
  58848.00   .005916  -.000434   .000000   .000000  -.022000   .006000
   .000000   .000000   .012000  -.007000 500.0000 500.0000 365.2500 182.6250
  37 0141 58989  58988 00000    -.433875
END NGA_COEFFICIENTS`

const EOPCommentsHeader = `# ----------------------------------------------------------------------------------------------------
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
#`

var taiUtcRegex = regexp.MustCompile(`(?i)JD\s+(\d+\.\d+)\s+TAI-UTC=\s*([\d\.-]+)\s*S\s*\+\s*\(MJD\s*-\s*([\d\.-]+)\.\)\s*X\s*([\d\.-e]+)\s*S`)

func parseTAIUTC(content string) []TAIUTCRecord {
	var records []TAIUTCRecord
	lines := strings.Split(content, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		matches := taiUtcRegex.FindStringSubmatch(line)
		if len(matches) == 5 {
			jd, err1 := strconv.ParseFloat(matches[1], 64)
			base, err2 := strconv.ParseFloat(matches[2], 64)
			anchor, err3 := strconv.ParseFloat(matches[3], 64)
			drift, err4 := strconv.ParseFloat(matches[4], 64)
			if err1 == nil && err2 == nil && err3 == nil && err4 == nil {
				mjd := int(math.Round(jd - 2400000.5))
				records = append(records, TAIUTCRecord{
					MJD:    mjd,
					Base:   base,
					Anchor: anchor,
					Drift:  drift,
				})
			}
		}
	}
	sort.Slice(records, func(i, j int) bool {
		return records[i].MJD < records[j].MJD
	})
	return records
}

func getDATForMJD(mjd int, taiUtcRecords []TAIUTCRecord) int {
	var activeRec *TAIUTCRecord
	for i := range taiUtcRecords {
		if taiUtcRecords[i].MJD <= mjd {
			activeRec = &taiUtcRecords[i]
		} else {
			break
		}
	}
	if activeRec == nil {
		return 0
	}
	val := activeRec.Base + float64(mjd-int(activeRec.Anchor))*activeRec.Drift
	return int(math.Round(val))
}

type EOPC04Record struct {
	Year   int
	Month  int
	Day    int
	MJD    int
	X      float64
	Y      float64
	UT1UTC float64
	Val8   float64
	Val9   float64
	LOD    float64
}

func parseEOPC04(content string) map[int]EOPC04Record {
	data := make(map[int]EOPC04Record)
	lines := strings.Split(content, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Fields(line)
		if len(parts) < 13 {
			continue
		}
		year, err0 := strconv.Atoi(parts[0])
		month, err1 := strconv.Atoi(parts[1])
		day, err2 := strconv.Atoi(parts[2])
		mjdVal, err3 := strconv.ParseFloat(parts[4], 64)
		if err0 != nil || err1 != nil || err2 != nil || err3 != nil {
			continue
		}
		mjd := int(math.Round(mjdVal))

		x, _ := strconv.ParseFloat(parts[5], 64)
		y, _ := strconv.ParseFloat(parts[6], 64)
		ut1Utc, _ := strconv.ParseFloat(parts[7], 64)
		val8, _ := strconv.ParseFloat(parts[8], 64)
		val9, _ := strconv.ParseFloat(parts[9], 64)
		lod, _ := strconv.ParseFloat(parts[12], 64)

		data[mjd] = EOPC04Record{
			Year:   year,
			Month:  month,
			Day:    day,
			MJD:    mjd,
			X:      x,
			Y:      y,
			UT1UTC: ut1Utc,
			Val8:   val8,
			Val9:   val9,
			LOD:    lod,
		}
	}
	return data
}

type BulletinAParserRecord struct {
	Year   int
	Month  int
	Day    int
	MJD    int
	X      float64
	Y      float64
	UT1UTC float64
	LOD    float64
	Val1   float64
	Val2   float64
	Type   string
}

func parseBulletinAFile(content string) map[int]BulletinAParserRecord {
	fileData := make(map[int]BulletinAParserRecord)
	lines := strings.Split(content, "\n")
	for _, line := range lines {
		if len(line) < 68 {
			continue
		}

		yearStr := strings.TrimSpace(line[0:2])
		monthStr := strings.TrimSpace(line[2:4])
		dayStr := strings.TrimSpace(line[4:6])
		mjdStr := strings.TrimSpace(line[7:15])
		if mjdStr == "" {
			continue
		}

		mjdFloat, err := strconv.ParseFloat(mjdStr, 64)
		if err != nil {
			continue
		}
		mjd := int(math.Round(mjdFloat))

		flagPM := line[16]
		if flagPM != 'I' && flagPM != 'P' {
			continue
		}

		xStr := strings.TrimSpace(line[18:27])
		x, _ := strconv.ParseFloat(xStr, 64)

		yStr := strings.TrimSpace(line[38:47])
		y, _ := strconv.ParseFloat(yStr, 64)

		utStr := strings.TrimSpace(line[58:68])
		ut1Utc, _ := strconv.ParseFloat(utStr, 64)

		var lod float64
		if len(line) >= 86 {
			lodStr := strings.TrimSpace(line[79:86])
			if lodStr != "" {
				lVal, err := strconv.ParseFloat(lodStr, 64)
				if err == nil {
					lod = lVal / 1000.0
				}
			}
		}

		var val1, val2 float64
		if len(line) >= 125 {
			v1Str := strings.TrimSpace(line[97:106])
			v2Str := strings.TrimSpace(line[116:125])
			if v1Str != "" {
				v, err := strconv.ParseFloat(v1Str, 64)
				if err == nil {
					val1 = v / 1000.0
				}
			}
			if v2Str != "" {
				v, err := strconv.ParseFloat(v2Str, 64)
				if err == nil {
					val2 = v / 1000.0
				}
			}
		}

		yy, _ := strconv.Atoi(yearStr)
		var year int
		if yy < 50 {
			year = 2000 + yy
		} else {
			year = 1900 + yy
		}

		month, _ := strconv.Atoi(monthStr)
		day, _ := strconv.Atoi(dayStr)

		dataType := "P"
		if flagPM == 'I' {
			dataType = "O"
		}

		fileData[mjd] = BulletinAParserRecord{
			Year:   year,
			Month:  month,
			Day:    day,
			MJD:    mjd,
			X:      x,
			Y:      y,
			UT1UTC: ut1Utc,
			LOD:    lod,
			Val1:   val1,
			Val2:   val2,
			Type:   dataType,
		}
	}
	return fileData
}

func parseBulletinA(content2000A, content1980 string) map[int]EOPRecord {
	dict2000A := parseBulletinAFile(content2000A)
	dict1980 := parseBulletinAFile(content1980)

	merged := make(map[int]EOPRecord)
	for mjd, item := range dict2000A {
		dpsi := 0.0
		deps := 0.0
		if item1980, ok := dict1980[mjd]; ok {
			dpsi = item1980.Val1
			deps = item1980.Val2
		}

		merged[mjd] = EOPRecord{
			Year:   item.Year,
			Month:  item.Month,
			Day:    item.Day,
			MJD:    mjd,
			X:      item.X,
			Y:      item.Y,
			UT1UTC: item.UT1UTC,
			LOD:    item.LOD,
			DPsi:   dpsi,
			DEps:   deps,
			DX:     item.Val1,
			DY:     item.Val2,
			Type:   item.Type,
		}
	}
	return merged
}

// EOPCompiler handles downloads and EOP compilation.
type EOPCompiler struct {
	CacheDir    string
	LogCallback func(string)
}

func (c *EOPCompiler) log(msg string) {
	if c.LogCallback != nil {
		c.LogCallback(msg)
	} else {
		fmt.Println(msg)
	}
}

func (c *EOPCompiler) downloadFile(urlStr, filename string) (string, error) {
	filePath := filepath.Join(c.CacheDir, filename)
	c.log(fmt.Sprintf("Fetching: %s", urlStr))

	_ = os.MkdirAll(c.CacheDir, 0755)

	client := &http.Client{Timeout: 30 * time.Second}
	req, err := http.NewRequest("GET", urlStr, nil)
	if err == nil {
		req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
		resp, err := client.Do(req)
		if err == nil && resp.StatusCode == http.StatusOK {
			defer resp.Body.Close()
			bodyBytes, err := io.ReadAll(resp.Body)
			if err == nil {
				content := string(bodyBytes)
				_ = os.WriteFile(filePath, bodyBytes, 0644)
				return content, nil
			}
		}
	}

	c.log(fmt.Sprintf("Download failed, checking local cache for: %s", filename))
	cachedBytes, err := os.ReadFile(filePath)
	if err == nil {
		return string(cachedBytes), nil
	}
	return "", fmt.Errorf("failed to retrieve file: %w", err)
}

// Compile compiles the EOP database.
func (c *EOPCompiler) Compile(offlineMode bool) (*EOPCompileResult, error) {
	if !offlineMode {
		c.log("Compile mode: Celestrak Direct Download. Skipping raw source build...")
		return c.compileFromCelestrak()
	}

	c.log("Starting Earth Orientation Parameters (EOP) compilation from raw IERS/USNO feeds...")
	// 1. Download
	taiUTCContent, err := c.downloadFile("https://maia.usno.navy.mil/ser7/tai-utc.dat", "tai_utc.dat")
	if err != nil {
		c.log(fmt.Sprintf("Raw feeds download failed: %v. Falling back to Celestrak...", err))
		return c.compileFromCelestrak()
	}

	c04StdContent, err := c.downloadFile("https://hpiers.obspm.fr/iers/eop/eopc04/eopc04.1962-now", "eopc04_std.txt")
	if err != nil {
		c.log(fmt.Sprintf("Raw feeds download failed: %v. Falling back to Celestrak...", err))
		return c.compileFromCelestrak()
	}

	c04DpsiContent, err := c.downloadFile("https://hpiers.obspm.fr/iers/eop/eopc04/eopc04.dPsi_dEps.1962-now", "eopc04_dpsi.txt")
	if err != nil {
		c.log(fmt.Sprintf("Raw feeds download failed: %v. Falling back to Celestrak...", err))
		return c.compileFromCelestrak()
	}

	finals2000AContent, err := c.downloadFile("https://maia.usno.navy.mil/ser7/finals2000A.all", "finals2000A.all")
	if err != nil {
		c.log(fmt.Sprintf("Raw feeds download failed: %v. Falling back to Celestrak...", err))
		return c.compileFromCelestrak()
	}

	finals1980Content, err := c.downloadFile("https://maia.usno.navy.mil/ser7/finals.all", "finals.all")
	if err != nil {
		c.log(fmt.Sprintf("Raw feeds download failed: %v. Falling back to Celestrak...", err))
		return c.compileFromCelestrak()
	}

	// 2. Parse
	c.log("Parsing raw datasets...")
	taiUtcRecords := parseTAIUTC(taiUTCContent)
	c04Std := parseEOPC04(c04StdContent)
	c04Dpsi := parseEOPC04(c04DpsiContent)
	bulletinA := parseBulletinA(finals2000AContent, finals1980Content)

	// 3. Merge C04 Observed
	c.log("Merging observed parameters...")
	observedMjdDict := make(map[int]EOPRecord)
	for mjd, stdRec := range c04Std {
		dpsi := 0.0
		deps := 0.0
		if dpsiRec, ok := c04Dpsi[mjd]; ok {
			dpsi = dpsiRec.Val8
			deps = dpsiRec.Val9
		}

		observedMjdDict[mjd] = EOPRecord{
			Year:   stdRec.Year,
			Month:  stdRec.Month,
			Day:    stdRec.Day,
			MJD:    mjd,
			X:      stdRec.X,
			Y:      stdRec.Y,
			UT1UTC: stdRec.UT1UTC,
			LOD:    stdRec.LOD,
			DPsi:   dpsi,
			DEps:   deps,
			DX:     stdRec.Val8,
			DY:     stdRec.Val9,
			Type:   "O",
		}
	}

	maxC04Mjd := 0
	for mjd := range observedMjdDict {
		if mjd > maxC04Mjd {
			maxC04Mjd = mjd
		}
	}
	c.log(fmt.Sprintf("Definitive Observed EOP (IERS C04) ends at MJD %d", maxC04Mjd))

	// 4. Partition Bulletin A
	var allObsMjds []int
	bulletinAObs := make(map[int]EOPRecord)
	bulletinAPred := make(map[int]EOPRecord)
	for mjd, r := range bulletinA {
		if r.Type == "O" {
			bulletinAObs[mjd] = r
			allObsMjds = append(allObsMjds, mjd)
		} else if r.Type == "P" {
			bulletinAPred[mjd] = r
		}
	}

	for mjd := range observedMjdDict {
		allObsMjds = append(allObsMjds, mjd)
	}

	if len(allObsMjds) == 0 {
		return nil, fmt.Errorf("no observed data found in feeds")
	}

	sort.Ints(allObsMjds)
	maxObsMjd := allObsMjds[len(allObsMjds)-1]
	minMjd := 37665 // 1962-01-01

	// 5. Build consolidations
	c.log("Constructing consolidated time-series...")
	var finalObserved []EOPRecord
	for mjd := minMjd; mjd <= maxObsMjd; mjd++ {
		var rec EOPRecord
		found := false
		if r, ok := observedMjdDict[mjd]; ok {
			rec = r
			found = true
		} else if r, ok := bulletinAObs[mjd]; ok {
			rec = r
			found = true
		}

		if found {
			dat := getDATForMJD(mjd, taiUtcRecords)
			rec.DAT = dat
			finalObserved = append(finalObserved, rec)
		}
	}

	var finalPredicted []EOPRecord
	predCount := 0
	currPredMjd := maxObsMjd + 1
	for predCount < 185 && currPredMjd < maxObsMjd+1000 {
		if rec, ok := bulletinAPred[currPredMjd]; ok {
			dat := getDATForMJD(currPredMjd, taiUtcRecords)
			rec.DAT = dat
			rec.Type = "P"
			finalPredicted = append(finalPredicted, rec)
			predCount++
		}
		currPredMjd++
	}

	c.log(fmt.Sprintf("Raw feeds compile successful. Observed=%d, Predicted=%d", len(finalObserved), len(finalPredicted)))
	return &EOPCompileResult{
		Observed:  finalObserved,
		Predicted: finalPredicted,
	}, nil
}

func (c *EOPCompiler) compileFromCelestrak() (*EOPCompileResult, error) {
	c.log("Downloading EOP-All.txt from CelesTrak...")
	url := "https://celestrak.org/SpaceData/EOP-All.txt"
	content, err := c.downloadFile(url, "celestrak_eop_all.txt")
	if err != nil {
		return nil, fmt.Errorf("failed downloading EOP-All: %w", err)
	}

	c.log("Parsing Celestrak EOP file...")
	var observed []EOPRecord
	var predicted []EOPRecord
	currentSection := ""

	lines := strings.Split(content, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		if line == "BEGIN OBSERVED" {
			currentSection = "OBS"
			continue
		} else if line == "END OBSERVED" {
			currentSection = ""
			continue
		} else if line == "BEGIN PREDICTED" {
			currentSection = "PRED"
			continue
		} else if line == "END PREDICTED" {
			currentSection = ""
			continue
		}

		if currentSection == "OBS" || currentSection == "PRED" {
			parts := strings.Fields(line)
			if len(parts) >= 13 {
				year, err0 := strconv.Atoi(parts[0])
				month, err1 := strconv.Atoi(parts[1])
				day, err2 := strconv.Atoi(parts[2])
				mjd, err3 := strconv.Atoi(parts[3])
				if err0 != nil || err1 != nil || err2 != nil || err3 != nil {
					continue
				}

				x, _ := strconv.ParseFloat(parts[4], 64)
				y, _ := strconv.ParseFloat(parts[5], 64)
				ut1Utc, _ := strconv.ParseFloat(parts[6], 64)
				lod, _ := strconv.ParseFloat(parts[7], 64)
				dpsi, _ := strconv.ParseFloat(parts[8], 64)
				deps, _ := strconv.ParseFloat(parts[9], 64)
				dx, _ := strconv.ParseFloat(parts[10], 64)
				dy, _ := strconv.ParseFloat(parts[11], 64)
				dat, _ := strconv.Atoi(parts[12])

				rec := EOPRecord{
					Year:   year,
					Month:  month,
					Day:    day,
					MJD:    mjd,
					X:      x,
					Y:      y,
					UT1UTC: ut1Utc,
					LOD:    lod,
					DPsi:   dpsi,
					DEps:   deps,
					DX:     dx,
					DY:     dy,
					DAT:    dat,
				}

				if currentSection == "OBS" {
					rec.Type = "O"
					observed = append(observed, rec)
				} else {
					rec.Type = "P"
					predicted = append(predicted, rec)
				}
			}
		}
	}

	c.log(fmt.Sprintf("Celestrak EOP parsing successful. Observed=%d, Predicted=%d", len(observed), len(predicted)))
	return &EOPCompileResult{
		Observed:  observed,
		Predicted: predicted,
	}, nil
}

// WriteToLegacyTXT writes data to legacy txt format (with NGA coefficients prepended by default).
func (c *EOPCompiler) WriteToLegacyTXT(data *EOPCompileResult, filePath string, legacyMode bool) error {
	var sb strings.Builder

	if legacyMode {
		sb.WriteString(NGALegacyCoefficients + "\n")
	}

	updatedStr := time.Now().UTC().Format("2006 Jan 02 15:04:05 UTC")
	sb.WriteString("VERSION 1.1\n")
	sb.WriteString(fmt.Sprintf("UPDATED %s\n", updatedStr))
	sb.WriteString(EOPCommentsHeader + "\n")

	sb.WriteString(fmt.Sprintf("NUM_OBSERVED_POINTS %d\n", len(data.Observed)))
	sb.WriteString("BEGIN OBSERVED\n")
	for _, r := range data.Observed {
		row := fmt.Sprintf("%4d %02d %02d %5d %9.6f %9.6f %10.7f %10.7f %9.6f %9.6f %9.6f %9.6f %3d\n",
			r.Year, r.Month, r.Day,
			r.MJD,
			r.X, r.Y,
			r.UT1UTC, r.LOD,
			r.DPsi, r.DEps,
			r.DX, r.DY,
			r.DAT,
		)
		sb.WriteString(row)
	}
	sb.WriteString("END OBSERVED\n\n")

	sb.WriteString(fmt.Sprintf("NUM_PREDICTED_POINTS %d\n", len(data.Predicted)))
	sb.WriteString("BEGIN PREDICTED\n")
	for _, r := range data.Predicted {
		row := fmt.Sprintf("%4d %02d %02d %5d %9.6f %9.6f %10.7f %10.7f %9.6f %9.6f %9.6f %9.6f %3d\n",
			r.Year, r.Month, r.Day,
			r.MJD,
			r.X, r.Y,
			r.UT1UTC, r.LOD,
			r.DPsi, r.DEps,
			r.DX, r.DY,
			r.DAT,
		)
		sb.WriteString(row)
	}
	sb.WriteString("END PREDICTED\n")

	err := os.MkdirAll(filepath.Dir(filepath.Clean(filePath)), 0755)
	if err != nil {
		return err
	}

	return os.WriteFile(filePath, []byte(sb.String()), 0644)
}

// WriteToCSV writes EOP compiled results to a CSV file.
func (c *EOPCompiler) WriteToCSV(data *EOPCompileResult, filePath string) error {
	var sb strings.Builder
	headers := []string{"DATE", "MJD", "X", "Y", "UT1-UTC", "LOD", "DPSI", "DEPS", "DX", "DY", "DAT", "DATA_TYPE"}
	sb.WriteString(strings.Join(headers, ",") + "\n")

	writeRow := func(r EOPRecord, dType string) {
		dateStr := fmt.Sprintf("%04d-%02d-%02d", r.Year, r.Month, r.Day)
		row := []string{
			dateStr, strconv.Itoa(r.MJD),
			fmt.Sprintf("%.6f", r.X), fmt.Sprintf("%.6f", r.Y),
			fmt.Sprintf("%.7f", r.UT1UTC), fmt.Sprintf("%.7f", r.LOD),
			fmt.Sprintf("%.6f", r.DPsi), fmt.Sprintf("%.6f", r.DEps),
			fmt.Sprintf("%.6f", r.DX), fmt.Sprintf("%.6f", r.DY),
			strconv.Itoa(r.DAT), dType,
		}
		sb.WriteString(strings.Join(row, ",") + "\n")
	}

	for _, r := range data.Observed {
		writeRow(r, "O")
	}
	for _, r := range data.Predicted {
		writeRow(r, "P")
	}

	err := os.MkdirAll(filepath.Dir(filepath.Clean(filePath)), 0755)
	if err != nil {
		return err
	}

	return os.WriteFile(filePath, []byte(sb.String()), 0644)
}

// EOPVerificationResult holds verification statistics.
type EOPVerificationResult struct {
	ObsMatchRate  float64  `json:"obs_match_rate"`
	PredMatchRate float64  `json:"pred_match_rate"`
	Discrepancies []string `json:"discrepancies"`
	IsLegacy      bool     `json:"is_legacy"`
}

// VerifyWithCelestrak verifies EOP data with Celestrak's live database.
func (c *EOPCompiler) VerifyWithCelestrak(generatedFilepath string) (*EOPVerificationResult, error) {
	c.log("Starting EOP compatibility check with CelesTrak live database...")

	celestrakContent, err := c.downloadFile("https://celestrak.org/SpaceData/EOP-All.txt", "celestrak_eop_all_verify.txt")
	if err != nil {
		return nil, fmt.Errorf("failed fetching Celestrak target: %w", err)
	}

	parseEOPSections := func(text string) (map[int]EOPRecord, map[int]EOPRecord) {
		obsDict := make(map[int]EOPRecord)
		predDict := make(map[int]EOPRecord)

		if strings.Contains(text, "BEGIN NGA_COEFFICIENTS") {
			parts := strings.Split(text, "END NGA_COEFFICIENTS")
			if len(parts) > 1 {
				text = parts[1]
			}
		}

		currentSection := ""
		lines := strings.Split(text, "\n")
		for _, line := range lines {
			line = strings.TrimSpace(line)
			if line == "" {
				continue
			}
			if line == "BEGIN OBSERVED" {
				currentSection = "OBS"
				continue
			} else if line == "END OBSERVED" {
				currentSection = ""
				continue
			} else if line == "BEGIN PREDICTED" {
				currentSection = "PRED"
				continue
			} else if line == "END PREDICTED" {
				currentSection = ""
				continue
			}

			if currentSection == "OBS" || currentSection == "PRED" {
				parts := strings.Fields(line)
				if len(parts) >= 13 {
					mjd, err := strconv.Atoi(parts[3])
					if err != nil {
						continue
					}
					x, _ := strconv.ParseFloat(parts[4], 64)
					y, _ := strconv.ParseFloat(parts[5], 64)
					ut1Utc, _ := strconv.ParseFloat(parts[6], 64)
					lod, _ := strconv.ParseFloat(parts[7], 64)
					dpsi, _ := strconv.ParseFloat(parts[8], 64)
					deps, _ := strconv.ParseFloat(parts[9], 64)
					dx, _ := strconv.ParseFloat(parts[10], 64)
					dy, _ := strconv.ParseFloat(parts[11], 64)
					dat, _ := strconv.Atoi(parts[12])

					rec := EOPRecord{
						X:      x,
						Y:      y,
						UT1UTC: ut1Utc,
						LOD:    lod,
						DPsi:   dpsi,
						DEps:   deps,
						DX:     dx,
						DY:     dy,
						DAT:    dat,
					}

					if currentSection == "OBS" {
						obsDict[mjd] = rec
					} else {
						predDict[mjd] = rec
					}
				}
			}
		}
		return obsDict, predDict
	}

	c.log("Parsing local and Celestrak files...")
	ctObs, ctPred := parseEOPSections(celestrakContent)

	localBytes, err := os.ReadFile(generatedFilepath)
	if err != nil {
		return nil, fmt.Errorf("failed reading local file: %w", err)
	}
	localContent := string(localBytes)
	localObs, localPred := parseEOPSections(localContent)

	c.log(fmt.Sprintf("Live Celestrak Points: OBS=%d, PRED=%d", len(ctObs), len(ctPred)))
	c.log(fmt.Sprintf("Local Generated Points: OBS=%d, PRED=%d", len(localObs), len(localPred)))

	var discrepancies []string
	matches := 0
	totalChecked := 0

	for mjd, cRec := range ctObs {
		if lRec, ok := localObs[mjd]; ok {
			totalChecked++

			diffX := math.Abs(cRec.X - lRec.X)
			diffY := math.Abs(cRec.Y - lRec.Y)
			diffUT := math.Abs(cRec.UT1UTC - lRec.UT1UTC)
			diffLOD := math.Abs(cRec.LOD - lRec.LOD)

			if diffX < 0.001 && diffY < 0.001 && diffUT < 0.001 && diffLOD < 0.001 && cRec.DAT == lRec.DAT {
				matches++
			} else {
				discrepancies = append(discrepancies,
					fmt.Sprintf("OBS MJD %d: CelesTrak=(x:%.6f, y:%.6f, UT1:%.7f, DAT:%d) Local=(x:%.6f, y:%.6f, UT1:%.7f, DAT:%d)",
						mjd, cRec.X, cRec.Y, cRec.UT1UTC, cRec.DAT, lRec.X, lRec.Y, lRec.UT1UTC, lRec.DAT),
				)
			}
		}
	}

	predMatches := 0
	predTotal := 0
	for mjd, cRec := range ctPred {
		if lRec, ok := localPred[mjd]; ok {
			predTotal++

			diffX := math.Abs(cRec.X - lRec.X)
			diffY := math.Abs(cRec.Y - lRec.Y)
			diffUT := math.Abs(cRec.UT1UTC - lRec.UT1UTC)

			if diffX < 0.01 && diffY < 0.01 && diffUT < 0.01 {
				predMatches++
			} else {
				discrepancies = append(discrepancies,
					fmt.Sprintf("PRED MJD %d: CelesTrak=(x:%.6f, y:%.6f, UT1:%.7f) Local=(x:%.6f, y:%.6f, UT1:%.7f)",
						mjd, cRec.X, cRec.Y, cRec.UT1UTC, lRec.X, lRec.Y, lRec.UT1UTC),
				)
			}
		}
	}

	obsRate := 0.0
	if totalChecked > 0 {
		obsRate = float64(matches) / float64(totalChecked)
	}

	predRate := 0.0
	if predTotal > 0 {
		predRate = float64(predMatches) / float64(predTotal)
	}

	c.log("\n--- EOP VERIFICATION REPORT ---")
	c.log(fmt.Sprintf("Observed Section Match: %d / %d (%.2f%%)", matches, totalChecked, obsRate*100))
	c.log(fmt.Sprintf("Predicted Section Match: %d / %d (%.2f%%)", predMatches, predTotal, predRate*100))
	c.log(fmt.Sprintf("Total Discrepancies: %d", len(discrepancies)))

	isLegacy := strings.Contains(localContent, "BEGIN NGA_COEFFICIENTS")

	return &EOPVerificationResult{
		ObsMatchRate:  obsRate,
		PredMatchRate: predRate,
		Discrepancies: discrepancies,
		IsLegacy:      isLegacy,
	}, nil
}
