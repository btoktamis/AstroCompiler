package spaceweather

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Record represents a single day's space weather parameters.
type Record struct {
	Date       string    `json:"date"`
	Year       int       `json:"year"`
	Month      int       `json:"month"`
	Day        int       `json:"day"`
	BSRN       int       `json:"bsrn"`
	ND         int       `json:"nd"`
	KpVals     []int     `json:"kp_vals"`
	ApVals     []int     `json:"ap_vals"`
	ApAvg      int       `json:"ap_avg"`
	ISN        int       `json:"isn"`
	F107Obs    float64   `json:"f107_obs"`
	F107Adj    float64   `json:"f107_adj"`
	F107ObsCtr float64   `json:"f107_obs_ctr"`
	F107ObsLst float64   `json:"f107_obs_last"`
	F107AdjCtr float64   `json:"f107_adj_ctr"`
	F107AdjLst float64   `json:"f107_adj_last"`
	QFlag      int       `json:"q_flag"`
	Source     string    `json:"source"`
}

// CompileResult holds observed, daily predicted, and monthly predicted datasets.
type CompileResult struct {
	Observed []Record `json:"observed"`
	Daily    []Record `json:"daily"`
	Monthly  []Record `json:"monthly"`
}

// Global conversion tables
var KpToApMap = map[int]int{
	0: 0, 3: 2, 7: 3, 10: 4, 13: 5, 17: 6, 20: 7, 23: 9, 27: 12, 30: 15,
	33: 18, 37: 22, 40: 27, 43: 32, 47: 39, 50: 48, 53: 56, 57: 67,
	60: 80, 63: 94, 70: 111, 73: 132, 77: 154, 80: 179, 83: 207,
	87: 236, 90: 300, 93: 400,
}

var ApToKpMap = map[int]int{
	0: 0, 2: 3, 3: 7, 4: 10, 5: 13, 6: 17, 7: 20, 9: 23, 12: 27, 15: 30,
	18: 33, 22: 37, 27: 40, 32: 43, 39: 47, 48: 50, 56: 53, 67: 57,
	80: 60, 94: 63, 111: 67, 132: 70, 154: 73, 179: 77, 207: 80,
	236: 83, 300: 87, 400: 90,
}

var XpAp = []int{0, 2, 3, 4, 5, 6, 7, 9, 12, 15, 18, 22, 27, 32, 39, 48, 56, 67, 80, 94, 111, 132, 154, 179, 207, 236, 300, 400}
var FpKp = []int{0, 3, 7, 10, 13, 17, 20, 23, 27, 30, 33, 37, 40, 43, 47, 50, 53, 57, 60, 63, 67, 70, 73, 77, 80, 83, 87, 90}

// ApToKp interpolates Kp from ap using standard table values.
// Returns Kp multiplied by 10 (e.g. 23 for 2.33).
func ApToKp(ap int) int {
	if val, ok := ApToKpMap[ap]; ok {
		return val
	}
	if ap <= 0 {
		return 0
	}
	if ap >= 400 {
		return 90
	}
	for i := 0; i < len(XpAp)-1; i++ {
		if XpAp[i] <= ap && ap <= XpAp[i+1] {
			x0, x1 := float64(XpAp[i]), float64(XpAp[i+1])
			y0, y1 := float64(FpKp[i]), float64(FpKp[i+1])
			y := y0 + (y1-y0)*(float64(ap)-x0)/(x1-x0)
			return int(math.Round(y))
		}
	}
	return 0
}

// ApSumToCp converts the daily sum of ap indices to the Cp character figure.
func ApSumToCp(apSum int) float64 {
	switch {
	case apSum <= 22:
		return 0.0
	case apSum <= 34:
		return 0.1
	case apSum <= 44:
		return 0.2
	case apSum <= 55:
		return 0.3
	case apSum <= 66:
		return 0.4
	case apSum <= 78:
		return 0.5
	case apSum <= 90:
		return 0.6
	case apSum <= 104:
		return 0.7
	case apSum <= 120:
		return 0.8
	case apSum <= 139:
		return 0.9
	case apSum <= 164:
		return 1.0
	case apSum <= 190:
		return 1.1
	case apSum <= 228:
		return 1.2
	case apSum <= 273:
		return 1.3
	case apSum <= 320:
		return 1.4
	case apSum <= 379:
		return 1.5
	case apSum <= 453:
		return 1.6
	case apSum <= 561:
		return 1.7
	case apSum <= 729:
		return 1.8
	case apSum <= 1119:
		return 1.9
	case apSum <= 1399:
		return 2.0
	case apSum <= 1699:
		return 2.1
	case apSum <= 1999:
		return 2.2
	case apSum <= 2399:
		return 2.3
	case apSum <= 3199:
		return 2.4
	default:
		return 2.5
	}
}

// CpToC9 converts the daily Cp character figure to the single-digit C9 index.
func CpToC9(cp float64) int {
	switch {
	case cp <= 0.1:
		return 0
	case cp <= 0.3:
		return 1
	case cp <= 0.5:
		return 2
	case cp <= 0.7:
		return 3
	case cp <= 0.9:
		return 4
	case cp <= 1.1:
		return 5
	case cp <= 1.4:
		return 6
	case cp <= 1.8:
		return 7
	case cp <= 1.9:
		return 8
	default:
		return 9
	}
}

// GetBartelsRotation calculates the Bartels Solar Rotation Number (BSRN)
// and Day within BSR (ND) for a given time. UTC cycle started 1832 Feb 8.
func GetBartelsRotation(t time.Time) (int, int) {
	startDate := time.Date(1832, 2, 8, 0, 0, 0, 0, time.UTC)
	tMidnight := time.Date(t.Year(), t.Month(), t.Day(), 12, 0, 0, 0, time.UTC)
	deltaDays := int(tMidnight.Sub(startDate).Hours() / 24.0)
	bsrn := 1 + deltaDays/27
	nd := 1 + deltaDays%27
	return bsrn, nd
}

// GetEarthSunDistance calculates the Earth-Sun distance in AU using J2000 orbital mechanics.
func GetEarthSunDistance(t time.Time) float64 {
	j2000 := time.Date(2000, 1, 1, 12, 0, 0, 0, time.UTC)
	deltaDays := t.Sub(j2000).Hours() / 24.0
	g := (357.529 + 0.98560028*deltaDays) * math.Pi / 180.0
	r := 1.00014 - 0.01671*math.Cos(g) - 0.00014*math.Cos(2*g)
	return r
}

// SpaceWeatherCompiler manages downloads and compilation.
type SpaceWeatherCompiler struct {
	CacheDir    string
	LogCallback func(string)
}

func (c *SpaceWeatherCompiler) log(msg string) {
	if c.LogCallback != nil {
		c.LogCallback(msg)
	} else {
		fmt.Println(msg)
	}
}

// downloadFile downloads url to cacheDir/filename. Falls back to cached file if download fails.
func (c *SpaceWeatherCompiler) downloadFile(urlStr, filename string) (string, error) {
	filePath := filepath.Join(c.CacheDir, filename)
	c.log(fmt.Sprintf("Fetching: %s", urlStr))

	// Ensure cache dir exists
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

	// Fallback
	c.log(fmt.Sprintf("Download failed, checking local cache for: %s", filename))
	cachedBytes, err := os.ReadFile(filePath)
	if err == nil {
		return string(cachedBytes), nil
	}
	return "", fmt.Errorf("failed to download and cache file: %w", err)
}

// fetchNASAPredictions downloads NASA SSN and F10.7 predictions with month-by-month fallback.
func (c *SpaceWeatherCompiler) fetchNASAPredictions() (string, string, error) {
	now := time.Now().UTC()
	monthsShort := []string{"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}

	for i := 0; i < 12; i++ {
		checkDate := now.AddDate(0, 0, -30*i)
		year := checkDate.Year()
		monthNum := fmt.Sprintf("%02d", checkDate.Month())
		monthName := monthsShort[checkDate.Month()-1]

		ssnURL := fmt.Sprintf("https://www.nasa.gov/wp-content/uploads/%d/%s/%s%dssn-prd.txt", year, monthNum, monthName, year)
		f107URL := fmt.Sprintf("https://www.nasa.gov/wp-content/uploads/%d/%s/%s%df10-prd.txt", year, monthNum, monthName, year)

		ssnContent, err1 := c.downloadFile(ssnURL, fmt.Sprintf("ssn_prd_%s%d.txt", monthName, year))
		if err1 != nil {
			continue
		}
		f107Content, err2 := c.downloadFile(f107URL, fmt.Sprintf("f10_prd_%s%d.txt", monthName, year))
		if err2 != nil {
			continue
		}

		c.log(fmt.Sprintf("Successfully loaded NASA predictions for %s %d", strings.ToUpper(monthName), year))
		return ssnContent, f107Content, nil
	}

	return "", "", fmt.Errorf("could not retrieve NASA predictions from the last 12 months")
}

func (c *SpaceWeatherCompiler) parseGFZ(content string) []Record {
	var records []Record
	lines := strings.Split(content, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Fields(line)
		if len(parts) < 28 {
			continue
		}

		year, err0 := strconv.Atoi(parts[0])
		month, err1 := strconv.Atoi(parts[1])
		day, err2 := strconv.Atoi(parts[2])
		if err0 != nil || err1 != nil || err2 != nil {
			continue
		}

		bsrn, _ := strconv.Atoi(parts[5])
		nd, _ := strconv.Atoi(parts[6])

		kpVals := make([]int, 8)
		for i := 0; i < 8; i++ {
			val, err := strconv.ParseFloat(parts[7+i], 64)
			if err != nil || val < 0 {
				kpVals[i] = -1
			} else {
				kpVals[i] = int(math.Round(val * 10))
			}
		}

		apVals := make([]int, 8)
		for i := 0; i < 8; i++ {
			apVals[i], _ = strconv.Atoi(parts[15+i])
		}

		apAvg, _ := strconv.Atoi(parts[23])
		isn, _ := strconv.Atoi(parts[24])

		f107Obs, _ := strconv.ParseFloat(parts[25], 64)
		f107Adj, _ := strconv.ParseFloat(parts[26], 64)

		records = append(records, Record{
			Date:    fmt.Sprintf("%d-%02d-%02d", year, month, day),
			Year:    year,
			Month:   month,
			Day:     day,
			BSRN:    bsrn,
			ND:      nd,
			KpVals:  kpVals,
			ApVals:  apVals,
			ApAvg:   apAvg,
			ISN:     isn,
			F107Obs: f107Obs,
			F107Adj: f107Adj,
			Source:  "GFZ",
		})
	}
	return records
}

type NOAA45DayItem struct {
	Time   string      `json:"time"`
	Metric string      `json:"metric"`
	Value  interface{} `json:"value"`
}
type NOAA45DayJSON struct {
	Data []NOAA45DayItem `json:"data"`
}

func (c *SpaceWeatherCompiler) parseNOAA45Day(content string) map[string]NOAAForecastVal {
	dataDict := make(map[string]NOAAForecastVal)
	var parsed NOAA45DayJSON
	err := json.Unmarshal([]byte(content), &parsed)
	if err != nil {
		c.log(fmt.Sprintf("Error parsing NOAA 45-day JSON: %v", err))
		return dataDict
	}

	for _, item := range parsed.Data {
		if len(item.Time) < 10 {
			continue
		}
		dateStr := item.Time[:10]
		val, ok := dataDict[dateStr]
		if !ok {
			val = NOAAForecastVal{Ap: 8, F10: 120.0} // defaults
		}

		var floatVal float64
		switch v := item.Value.(type) {
		case float64:
			floatVal = v
		case string:
			floatVal, _ = strconv.ParseFloat(v, 64)
		}

		if item.Metric == "ap" {
			val.Ap = int(floatVal)
		} else if item.Metric == "f107" {
			val.F10 = floatVal
		}
		dataDict[dateStr] = val
	}
	return dataDict
}

type NOAA3HrItem struct {
	TimeTag string  `json:"time_tag"`
	Kp      float64 `json:"kp"`
}

func (c *SpaceWeatherCompiler) parseNOAA3Hr(content string) map[string][]float64 {
	forecast := make(map[string][]float64)
	var parsed []NOAA3HrItem
	err := json.Unmarshal([]byte(content), &parsed)
	if err != nil {
		c.log(fmt.Sprintf("Error parsing NOAA 3-hour JSON: %v", err))
		return forecast
	}

	for _, item := range parsed {
		if len(item.TimeTag) < 13 {
			continue
		}
		t, err := time.Parse("2006-01-02T15:04:05", item.TimeTag)
		if err != nil {
			t, err = time.Parse("2006-01-02T15", item.TimeTag[:13])
			if err != nil {
				continue
			}
		}
		dateKey := t.Format("2006-01-02")
		hour := t.Hour()
		idx := hour / 3

		vals, ok := forecast[dateKey]
		if !ok {
			vals = make([]float64, 8)
			for j := 0; j < 8; j++ {
				vals[j] = -1.0
			}
		}
		if idx >= 0 && idx < 8 {
			vals[idx] = item.Kp
		}
		forecast[dateKey] = vals
	}
	return forecast
}

func (c *SpaceWeatherCompiler) parseNASATable(content string) map[string]float64 {
	predictions := make(map[string]float64)
	monthsMap := map[string]int{
		"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
		"JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
	}

	lines := strings.Split(content, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "TABLE") || strings.HasPrefix(line, "TIME") || strings.HasPrefix(line, "PERCENTILE") {
			continue
		}
		parts := strings.Fields(line)
		if len(parts) < 4 {
			continue
		}

		mStr := strings.ToUpper(parts[1])
		monthNum, ok := monthsMap[mStr]
		if !ok {
			continue
		}

		timeFrac, err := strconv.ParseFloat(parts[0], 64)
		if err != nil {
			continue
		}

		year := int(math.Floor(timeFrac))
		val, err := strconv.ParseFloat(parts[3], 64) // 50th percentile
		if err != nil {
			continue
		}

		monthKey := fmt.Sprintf("%d-%02d", year, monthNum)
		predictions[monthKey] = val
	}
	return predictions
}

type NOAAForecastVal struct {
	Ap  int
	F10 float64
}

func interpolateSeries(series []float64) []float64 {
	result := make([]float64, len(series))
	copy(result, series)

	var validIndices []int
	for i, val := range result {
		if val > 0 {
			validIndices = append(validIndices, i)
		}
	}

	if len(validIndices) == 0 {
		return result
	}

	for k := 0; k < len(validIndices)-1; k++ {
		idx0 := validIndices[k]
		idx1 := validIndices[k+1]
		if idx1-idx0 > 1 {
			y0 := result[idx0]
			y1 := result[idx1]
			for idx := idx0 + 1; idx < idx1; idx++ {
				result[idx] = y0 + (y1-y0)*float64(idx-idx0)/float64(idx1-idx0)
			}
		}
	}

	// Extrapolate boundaries
	firstIdx := validIndices[0]
	for idx := 0; idx < firstIdx; idx++ {
		result[idx] = result[firstIdx]
	}

	lastIdx := validIndices[len(validIndices)-1]
	for idx := lastIdx + 1; idx < len(result); idx++ {
		result[idx] = result[lastIdx]
	}

	return result
}

type timelineItem struct {
	obs      float64
	adj      float64
	obsCtr   float64
	adjCtr   float64
	obsLast  float64
	adjLast  float64
	dataType string
}

// Compile executes the compilation pipeline.
func (c *SpaceWeatherCompiler) Compile() (*CompileResult, error) {
	c.log("Starting space weather compilation...")

	// 1. Fetch
	gfzHistContent, err := c.downloadFile("https://www-app3.gfz-potsdam.de/kp_index/Kp_ap_Ap_SN_F107_since_1932.txt", "gfz_since_1932.txt")
	if err != nil {
		return nil, fmt.Errorf("failed fetching historical GFZ: %w", err)
	}

	var gfzNowcastContent string
	nowcastRes, errNowcast := c.downloadFile("https://www-app3.gfz-potsdam.de/kp_index/Kp_ap_Ap_SN_F107_nowcast.txt", "gfz_nowcast.txt")
	if errNowcast == nil {
		gfzNowcastContent = nowcastRes
	}

	noaa45DayContent, err := c.downloadFile("https://services.swpc.noaa.gov/json/45-day-forecast.json", "noaa_45day.json")
	if err != nil {
		return nil, fmt.Errorf("failed fetching NOAA 45day: %w", err)
	}

	noaa3HrContent, err := c.downloadFile("https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json", "noaa_3hr.json")
	if err != nil {
		return nil, fmt.Errorf("failed fetching NOAA 3hr: %w", err)
	}

	nasaSSNContent, nasaF107Content, err := c.fetchNASAPredictions()
	if err != nil {
		return nil, fmt.Errorf("failed fetching NASA predictions: %w", err)
	}

	// 2. Parse
	records := c.parseGFZ(gfzHistContent)
	if gfzNowcastContent != "" {
		nowcastRecords := c.parseGFZ(gfzNowcastContent)
		gfzDict := make(map[string]Record)
		for _, r := range records {
			gfzDict[r.Date] = r
		}
		for _, nr := range nowcastRecords {
			gfzDict[nr.Date] = nr
		}

		// Re-sort
		records = make([]Record, 0, len(gfzDict))
		for _, r := range gfzDict {
			records = append(records, r)
		}
		sort.Slice(records, func(i, j int) bool {
			return records[i].Date < records[j].Date
		})
	}

	noaa45day := c.parseNOAA45Day(noaa45DayContent)
	noaa3hr := c.parseNOAA3Hr(noaa3HrContent)
	nasaSSN := c.parseNASATable(nasaSSNContent)
	nasaF107 := c.parseNASATable(nasaF107Content)

	// 3. Filter observed
	startDate := "1957-10-01"
	var observedRecords []Record
	for _, r := range records {
		if r.Date >= startDate {
			observedRecords = append(observedRecords, r)
		}
	}

	if len(observedRecords) == 0 {
		return nil, fmt.Errorf("no observed records found since 1957-10-01")
	}

	lastObservedDateStr := observedRecords[len(observedRecords)-1].Date
	c.log(fmt.Sprintf("Observed data goes from 1957-10-01 to %s", lastObservedDateStr))

	// 4. Generate Daily predictions (45 days)
	var dailyPredicted []Record
	lastObservedDT, err := time.Parse("2006-01-02", lastObservedDateStr)
	if err != nil {
		return nil, fmt.Errorf("error parsing last observed date: %w", err)
	}
	lastObservedDT = lastObservedDT.UTC()

	for i := 1; i <= 45; i++ {
		predDT := lastObservedDT.AddDate(0, 0, i)
		predDateStr := predDT.Format("2006-01-02")

		bsrn, nd := GetBartelsRotation(predDT)
		year, month, day := predDT.Year(), int(predDT.Month()), predDT.Day()

		noaaVals, ok := noaa45day[predDateStr]
		if !ok {
			noaaVals = NOAAForecastVal{Ap: 8, F10: 120.0}
		}
		apAvg := noaaVals.Ap
		f107Adj := noaaVals.F10

		kpVals := make([]int, 8)
		apVals := make([]int, 8)

		if kpForecast, ok := noaa3hr[predDateStr]; ok {
			for idx, kpF := range kpForecast {
				var kpVal, apVal int
				if kpF < 0 {
					apVal = apAvg
					kpVal = ApToKp(apVal)
				} else {
					kpVal = int(math.Round(kpF * 10))
					apVal = 0
					minDiff := 9999
					for kpM, apM := range KpToApMap {
						if int(math.Abs(float64(kpM-kpVal))) < minDiff {
							minDiff = int(math.Abs(float64(kpM - kpVal)))
							apVal = apM
						}
					}
				}
				kpVals[idx] = kpVal
				apVals[idx] = apVal
			}
		} else {
			for idx := 0; idx < 8; idx++ {
				apVals[idx] = apAvg
				kpVals[idx] = ApToKp(apAvg)
			}
		}

		kpSum := 0
		for _, v := range kpVals {
			kpSum += v
		}

		monthKey := fmt.Sprintf("%d-%02d", year, month)
		isnFloat, ok := nasaSSN[monthKey]
		if !ok {
			isnFloat = 70.0
		}
		isn := int(math.Round(isnFloat))

		rDist := GetEarthSunDistance(predDT)
		f107Obs := f107Adj / (rDist * rDist)

		dailyPredicted = append(dailyPredicted, Record{
			Date:    predDateStr,
			Year:    year,
			Month:   month,
			Day:     day,
			BSRN:    bsrn,
			ND:      nd,
			KpVals:  kpVals,
			ApVals:  apVals,
			ApAvg:   apAvg,
			ISN:     isn,
			F107Obs: f107Obs,
			F107Adj: f107Adj,
			Source:  "NOAA_PRED",
		})
	}

	// 5. Generate Monthly predictions (~18 years)
	var monthlyPredicted []Record
	lastDailyDT, _ := time.Parse("2006-01-02", dailyPredicted[len(dailyPredicted)-1].Date)
	lastDailyDT = lastDailyDT.UTC()

	var startMonthlyYear, startMonthlyMonth int
	if lastDailyDT.Month() == 12 {
		startMonthlyYear = lastDailyDT.Year() + 1
		startMonthlyMonth = 1
	} else {
		startMonthlyYear = lastDailyDT.Year()
		startMonthlyMonth = int(lastDailyDT.Month()) + 1
	}

	currentMonthlyDT := time.Date(startMonthlyYear, time.Month(startMonthlyMonth), 1, 12, 0, 0, 0, time.UTC)

	for m := 0; m < 220; m++ {
		year := currentMonthlyDT.Year()
		month := int(currentMonthlyDT.Month())
		monthKey := fmt.Sprintf("%d-%02d", year, month)

		f107Val, okF10 := nasaF107[monthKey]
		ssnVal, okSSN := nasaSSN[monthKey]
		if !okF10 || !okSSN {
			break
		}

		bsrn, nd := GetBartelsRotation(currentMonthlyDT)
		isn := int(math.Round(ssnVal))
		f107Adj := f107Val

		rDist := GetEarthSunDistance(currentMonthlyDT)
		f107Obs := f107Adj / (rDist * rDist)

		monthlyPredicted = append(monthlyPredicted, Record{
			Date:    currentMonthlyDT.Format("2006-01-02"),
			Year:    year,
			Month:   month,
			Day:     1,
			BSRN:    bsrn,
			ND:      nd,
			ISN:     isn,
			F107Obs: f107Obs,
			F107Adj: f107Adj,
			Source:  "NASA_PRED",
		})

		currentMonthlyDT = currentMonthlyDT.AddDate(0, 1, 0)
	}

	// 6. Moving Averages Calculation
	n := len(observedRecords)
	var timeline []timelineItem
	for _, r := range observedRecords {
		timeline = append(timeline, timelineItem{obs: r.F107Obs, adj: r.F107Adj, dataType: "OBS"})
	}
	for _, r := range dailyPredicted {
		timeline = append(timeline, timelineItem{obs: r.F107Obs, adj: r.F107Adj, dataType: "DAILY"})
	}

	// Pad timeline with monthly predictions to allow centering over predictions
	monthlyMap := make(map[string]Record)
	for _, m := range monthlyPredicted {
		monthlyMap[m.Date[:7]] = m
	}

	lastDT := lastDailyDT
	for j := 1; j < 100; j++ {
		futDT := lastDT.AddDate(0, 0, j)
		fKey := futDT.Format("2006-01")
		if mVal, ok := monthlyMap[fKey]; ok {
			timeline = append(timeline, timelineItem{obs: mVal.F107Obs, adj: mVal.F107Adj, dataType: "MONTH_FILL"})
		} else {
			lastDaily := dailyPredicted[len(dailyPredicted)-1]
			timeline = append(timeline, timelineItem{obs: lastDaily.F107Obs, adj: lastDaily.F107Adj, dataType: "MONTH_FILL"})
		}
	}

	// Interpolate observed section
	obsSeries := make([]float64, len(timeline))
	adjSeries := make([]float64, len(timeline))
	for i, t := range timeline {
		obsSeries[i] = t.obs
		adjSeries[i] = t.adj
	}

	obsInterp := interpolateSeries(obsSeries[:n])
	adjInterp := interpolateSeries(adjSeries[:n])

	for i := 0; i < n; i++ {
		timeline[i].obs = obsInterp[i]
		timeline[i].adj = adjInterp[i]
	}

	// Calculate averages
	for i := 0; i < len(timeline); i++ {
		// Centered 81-day average
		if i >= 40 && i < len(timeline)-40 {
			sumObs := 0.0
			sumAdj := 0.0
			for k := i - 40; k <= i+40; k++ {
				sumObs += timeline[k].obs
				sumAdj += timeline[k].adj
			}
			timeline[i].obsCtr = sumObs / 81.0
			timeline[i].adjCtr = sumAdj / 81.0
		} else {
			timeline[i].obsCtr = timeline[i].obs
			timeline[i].adjCtr = timeline[i].adj
		}

		// Last 81-day average
		if i >= 80 {
			sumObs := 0.0
			sumAdj := 0.0
			for k := i - 80; k <= i; k++ {
				sumObs += timeline[k].obs
				sumAdj += timeline[k].adj
			}
			timeline[i].obsLast = sumObs / 81.0
			timeline[i].adjLast = sumAdj / 81.0
		} else {
			timeline[i].obsLast = timeline[i].obs
			timeline[i].adjLast = timeline[i].adj
		}
	}

	// Write averages back to observed
	for idx := range observedRecords {
		origVal := records[idx+(len(records)-len(observedRecords))].F107Obs
		if origVal <= 0 {
			observedRecords[idx].QFlag = 4 // Interpolated
		} else {
			observedRecords[idx].QFlag = 0 // Observed
		}

		observedRecords[idx].F107Obs = timeline[idx].obs
		observedRecords[idx].F107Adj = timeline[idx].adj
		observedRecords[idx].F107ObsCtr = timeline[idx].obsCtr
		observedRecords[idx].F107ObsLst = timeline[idx].obsLast
		observedRecords[idx].F107AdjCtr = timeline[idx].adjCtr
		observedRecords[idx].F107AdjLst = timeline[idx].adjLast
	}

	// Write back to daily predictions
	for idx := range dailyPredicted {
		tIdx := n + idx
		dailyPredicted[idx].QFlag = 2 // Predicted fallback
		dailyPredicted[idx].F107Obs = timeline[tIdx].obs
		dailyPredicted[idx].F107Adj = timeline[tIdx].adj
		dailyPredicted[idx].F107ObsCtr = timeline[tIdx].obsCtr
		dailyPredicted[idx].F107ObsLst = timeline[tIdx].obsLast
		dailyPredicted[idx].F107AdjCtr = timeline[tIdx].adjCtr
		dailyPredicted[idx].F107AdjLst = timeline[tIdx].adjLast
	}

	// Fill monthly predictions defaults
	for idx := range monthlyPredicted {
		monthlyPredicted[idx].F107ObsCtr = monthlyPredicted[idx].F107Obs
		monthlyPredicted[idx].F107ObsLst = monthlyPredicted[idx].F107Obs
		monthlyPredicted[idx].F107AdjCtr = monthlyPredicted[idx].F107Adj
		monthlyPredicted[idx].F107AdjLst = monthlyPredicted[idx].F107Adj
		monthlyPredicted[idx].QFlag = 2
	}

	c.log(fmt.Sprintf("Compilation finished. Observed=%d, Daily=%d, Monthly=%d", len(observedRecords), len(dailyPredicted), len(monthlyPredicted)))

	return &CompileResult{
		Observed: observedRecords,
		Daily:    dailyPredicted,
		Monthly:  monthlyPredicted,
	}, nil
}

// WriteToLegacyTXT writes compiled data to SW-All.txt legacy fixed-width format.
func (c *SpaceWeatherCompiler) WriteToLegacyTXT(data *CompileResult, filePath string) error {
	var sb strings.Builder

	updatedStr := time.Now().UTC().Format("2006 Jan 02 15:04:05 UTC")
	sb.WriteString("DATATYPE CssiSpaceWeather\n\n")
	sb.WriteString("VERSION 1.2\n\n")
	sb.WriteString(fmt.Sprintf("UPDATED %s\n\n", updatedStr))
	sb.WriteString("# --------------------------------------------------------------------------------------------------------------------------------\n")
	sb.WriteString("#                              SPACE WEATHER DATA\n")
	sb.WriteString("# --------------------------------------------------------------------------------------------------------------------------------\n")
	sb.WriteString("#\n")
	sb.WriteString("# See https://celestrak.org/SpaceData/SpaceWx-format.php for format details.\n")
	sb.WriteString("#\n")
	sb.WriteString("# FORMAT(I4,I3,I3,I5,I3,8I3,I4,8I4,I4,F4.1,I2,I4,F6.1,I2,5F6.1)\n")
	sb.WriteString("# --------------------------------------------------------------------------------------------------------------------------------\n")
	sb.WriteString("#                                                                                             Adj     Adj   Adj   Obs   Obs   Obs \n")
	sb.WriteString("# yy mm dd BSRN ND Kp Kp Kp Kp Kp Kp Kp Kp Sum Ap  Ap  Ap  Ap  Ap  Ap  Ap  Ap  Avg Cp C9 ISN F10.7 Q Ctr81 Lst81 F10.7 Ctr81 Lst81\n")
	sb.WriteString("# --------------------------------------------------------------------------------------------------------------------------------\n")
	sb.WriteString("#\n\n")

	sb.WriteString(fmt.Sprintf("NUM_OBSERVED_POINTS %d\n", len(data.Observed)))
	sb.WriteString("BEGIN OBSERVED\n")

	for _, r := range data.Observed {
		apSum := 0
		for _, v := range r.ApVals {
			apSum += v
		}
		cp := ApSumToCp(apSum)
		c9 := CpToC9(cp)

		kpStr := ""
		for _, v := range r.KpVals {
			if v >= 0 {
				kpStr += fmt.Sprintf("%3d", v)
			} else {
				kpStr += "   "
			}
		}

		kpSumVal := 0
		kpSumAllValid := true
		for _, v := range r.KpVals {
			if v < 0 {
				kpSumAllValid = false
			}
			kpSumVal += v
		}

		kpSumStr := "    "
		if kpSumAllValid {
			kpSumStr = fmt.Sprintf("%4d", kpSumVal)
		}

		apStr := ""
		for _, v := range r.ApVals {
			apStr += fmt.Sprintf("%4d", v)
		}

		row := fmt.Sprintf("%4d %02d %02d%5d%3d%s%s%s%4d%4.1f%2d%4d%6.1f%2d%6.1f%6.1f%6.1f%6.1f%6.1f\n",
			r.Year, r.Month, r.Day,
			r.BSRN, r.ND,
			kpStr, kpSumStr, apStr,
			r.ApAvg, cp, c9, r.ISN,
			r.F107Adj, r.QFlag,
			r.F107AdjCtr, r.F107AdjLst,
			r.F107Obs, r.F107ObsCtr, r.F107ObsLst,
		)
		sb.WriteString(row)
	}
	sb.WriteString("END OBSERVED\n\n")

	sb.WriteString(fmt.Sprintf("NUM_DAILY_PREDICTED_POINTS %d\n", len(data.Daily)))
	sb.WriteString("BEGIN DAILY_PREDICTED\n")

	for _, r := range data.Daily {
		apSum := 0
		for _, v := range r.ApVals {
			apSum += v
		}
		cp := ApSumToCp(apSum)
		c9 := CpToC9(cp)

		kpStr := ""
		for _, v := range r.KpVals {
			kpStr += fmt.Sprintf("%3d", v)
		}

		kpSumVal := 0
		for _, v := range r.KpVals {
			kpSumVal += v
		}
		kpSumStr := fmt.Sprintf("%4d", kpSumVal)

		apStr := ""
		for _, v := range r.ApVals {
			apStr += fmt.Sprintf("%4d", v)
		}

		row := fmt.Sprintf("%4d %02d %02d%5d%3d%s%s%s%4d%4.1f%2d%4d%6.1f  %6.1f%6.1f%6.1f%6.1f%6.1f\n",
			r.Year, r.Month, r.Day,
			r.BSRN, r.ND,
			kpStr, kpSumStr, apStr,
			r.ApAvg, cp, c9, r.ISN,
			r.F107Adj,
			r.F107AdjCtr, r.F107AdjLst,
			r.F107Obs, r.F107ObsCtr, r.F107ObsLst,
		)
		sb.WriteString(row)
	}
	sb.WriteString("END DAILY_PREDICTED\n\n")

	sb.WriteString(fmt.Sprintf("NUM_MONTHLY_PREDICTED_POINTS %d\n", len(data.Monthly)))
	sb.WriteString("BEGIN MONTHLY_PREDICTED\n")

	for _, r := range data.Monthly {
		blankField := strings.Repeat(" ", 70) // spaces for Kp, ap, Cp, C9 fields

		row := fmt.Sprintf("%4d %02d %02d%5d%3d%s%4d%6.1f  %6.1f%6.1f%6.1f%6.1f%6.1f\n",
			r.Year, r.Month, r.Day,
			r.BSRN, r.ND,
			blankField, r.ISN,
			r.F107Adj,
			r.F107AdjCtr, r.F107AdjLst,
			r.F107Obs, r.F107ObsCtr, r.F107ObsLst,
		)
		sb.WriteString(row)
	}
	sb.WriteString("END MONTHLY_PREDICTED\n")

	// Ensure directories exist
	err := os.MkdirAll(filepath.Dir(filepath.Clean(filePath)), 0755)
	if err != nil {
		return err
	}

	return os.WriteFile(filePath, []byte(sb.String()), 0644)
}

// WriteToCSV writes compiled data to a CSV spreadsheet.
func (c *SpaceWeatherCompiler) WriteToCSV(data *CompileResult, filePath string) error {
	var sb strings.Builder

	headers := []string{
		"DATE", "BSRN", "ND",
		"KP1", "KP2", "KP3", "KP4", "KP5", "KP6", "KP7", "KP8", "KP_SUM",
		"AP1", "AP2", "AP3", "AP4", "AP5", "AP6", "AP7", "AP8", "AP_AVG",
		"CP", "C9", "ISN", "F107_ADJ", "Q_FLAG",
		"F107_ADJ_CTR81", "F107_ADJ_LST81", "F107_OBS", "F107_OBS_CTR81", "F107_OBS_LST81",
		"DATA_TYPE",
	}
	sb.WriteString(strings.Join(headers, ",") + "\n")

	// Helper to format record
	writeRecord := func(r Record, dType string) {
		kpSumVal := 0
		kpSumAllValid := true
		var kps []string
		for _, v := range r.KpVals {
			if v < 0 {
				kpSumAllValid = false
				kps = append(kps, "")
			} else {
				kps = append(kps, strconv.Itoa(v))
				kpSumVal += v
			}
		}
		kpSumStr := ""
		if kpSumAllValid && len(r.KpVals) > 0 {
			kpSumStr = strconv.Itoa(kpSumVal)
		}

		var aps []string
		apSum := 0
		for _, v := range r.ApVals {
			aps = append(aps, strconv.Itoa(v))
			apSum += v
		}

		cpVal := ApSumToCp(apSum)
		c9Val := CpToC9(cpVal)

		cpStr := fmt.Sprintf("%.1f", cpVal)
		c9Str := strconv.Itoa(c9Val)
		if dType == "M" {
			cpStr = ""
			c9Str = ""
		}

		row := []string{
			r.Date, strconv.Itoa(r.BSRN), strconv.Itoa(r.ND),
		}
		if dType != "M" {
			row = append(row, kps...)
			row = append(row, kpSumStr)
			row = append(row, aps...)
			row = append(row, strconv.Itoa(r.ApAvg))
			row = append(row, cpStr, c9Str)
		} else {
			// Blank out Kp, ap, Cp, C9 fields (8 + 1 + 8 + 1 + 2 = 20 columns)
			for i := 0; i < 20; i++ {
				row = append(row, "")
			}
		}

		row = append(row,
			strconv.Itoa(r.ISN),
			fmt.Sprintf("%.1f", r.F107Adj),
			strconv.Itoa(r.QFlag),
			fmt.Sprintf("%.1f", r.F107AdjCtr),
			fmt.Sprintf("%.1f", r.F107AdjLst),
			fmt.Sprintf("%.1f", r.F107Obs),
			fmt.Sprintf("%.1f", r.F107ObsCtr),
			fmt.Sprintf("%.1f", r.F107ObsLst),
			dType,
		)
		sb.WriteString(strings.Join(row, ",") + "\n")
	}

	for _, r := range data.Observed {
		writeRecord(r, "O")
	}
	for _, r := range data.Daily {
		writeRecord(r, "D")
	}
	for _, r := range data.Monthly {
		writeRecord(r, "M")
	}

	err := os.MkdirAll(filepath.Dir(filepath.Clean(filePath)), 0755)
	if err != nil {
		return err
	}

	return os.WriteFile(filePath, []byte(sb.String()), 0644)
}

// VerificationResult contains the verification metrics.
type VerificationResult struct {
	ObsMatchRate  float64  `json:"obs_match_rate"`
	PredMatchRate float64  `json:"pred_match_rate"`
	Discrepancies []string `json:"discrepancies"`
}

// VerifyWithCelestrak compares generated file with live database.
func (c *SpaceWeatherCompiler) VerifyWithCelestrak(generatedFilepath string) (*VerificationResult, error) {
	c.log("Starting compatibility check with CelesTrak...")

	celestrakContent, err := c.downloadFile("https://celestrak.org/SpaceData/SW-All.txt", "celestrak_sw_all_target.txt")
	if err != nil {
		return nil, fmt.Errorf("failed fetching Celestrak target: %w", err)
	}

	parseLegacyContent := func(content string) (map[string]string, map[string]string, map[string]string) {
		obs := make(map[string]string)
		daily := make(map[string]string)
		monthly := make(map[string]string)

		lines := strings.Split(content, "\n")
		currentSection := ""
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
			} else if line == "BEGIN DAILY_PREDICTED" {
				currentSection = "DAILY"
				continue
			} else if line == "END DAILY_PREDICTED" {
				currentSection = ""
				continue
			} else if line == "BEGIN MONTHLY_PREDICTED" {
				currentSection = "MONTHLY"
				continue
			} else if line == "END MONTHLY_PREDICTED" {
				currentSection = ""
				continue
			}

			if currentSection != "" {
				parts := strings.Fields(line)
				if len(parts) >= 3 {
					// Build YYYY-MM-DD
					yearVal, _ := strconv.Atoi(parts[0])
					monthVal, _ := strconv.Atoi(parts[1])
					dayVal, _ := strconv.Atoi(parts[2])
					dateKey := fmt.Sprintf("%d-%02d-%02d", yearVal, monthVal, dayVal)

					// Pad line if short for string indexing
					padded := line
					if len(line) < 130 {
						padded = line + strings.Repeat(" ", 130-len(line))
					}

					switch currentSection {
					case "OBS":
						obs[dateKey] = padded
					case "DAILY":
						daily[dateKey] = padded
					case "MONTHLY":
						monthly[dateKey] = padded
					}
				}
			}
		}
		return obs, daily, monthly
	}

	offObs, offDaily, _ := parseLegacyContent(celestrakContent)

	genContentBytes, err := os.ReadFile(generatedFilepath)
	if err != nil {
		return nil, fmt.Errorf("failed reading generated file: %w", err)
	}
	genObs, genDaily, _ := parseLegacyContent(string(genContentBytes))

	c.log(fmt.Sprintf("Official file points: OBS=%d, DAILY=%d", len(offObs), len(offDaily)))
	c.log(fmt.Sprintf("Generated file points: OBS=%d, DAILY=%d", len(genObs), len(genDaily)))

	var discrepancies []string
	matches := 0
	totalChecked := 0

	for dateKey, offLine := range offObs {
		if genLine, ok := genObs[dateKey]; ok {
			totalChecked++

			if len(offLine) < 118 || len(genLine) < 118 {
				discrepancies = append(discrepancies, fmt.Sprintf("OBS %s: Line lengths insufficient: off=%d, gen=%d", dateKey, len(offLine), len(genLine)))
				continue
			}

			offAvg, _ := strconv.Atoi(strings.TrimSpace(offLine[78:82]))
			genAvg, _ := strconv.Atoi(strings.TrimSpace(genLine[78:82]))

			offISN, _ := strconv.Atoi(strings.TrimSpace(offLine[88:92]))
			genISN, _ := strconv.Atoi(strings.TrimSpace(genLine[88:92]))

			offAdj, _ := strconv.ParseFloat(strings.TrimSpace(offLine[92:98]), 64)
			genAdj, _ := strconv.ParseFloat(strings.TrimSpace(genLine[92:98]), 64)

			offObsVal, _ := strconv.ParseFloat(strings.TrimSpace(offLine[112:118]), 64)
			genObsVal, _ := strconv.ParseFloat(strings.TrimSpace(genLine[112:118]), 64)

			diffAvg := math.Abs(float64(offAvg - genAvg))
			diffISN := math.Abs(float64(offISN - genISN))
			diffAdj := math.Abs(offAdj - genAdj)
			diffObs := math.Abs(offObsVal - genObsVal)

			if diffAvg <= 1.0 && diffISN <= 2.0 && diffAdj <= 0.2 && diffObs <= 0.2 {
				matches++
			} else {
				discrepancies = append(discrepancies,
					fmt.Sprintf("OBS %s: CelesTrak=(AvgAp:%d, ISN:%d, AdjFlux:%.1f, ObsFlux:%.1f) Local=(AvgAp:%d, ISN:%d, AdjFlux:%.1f, ObsFlux:%.1f)",
						dateKey, offAvg, offISN, offAdj, offObsVal, genAvg, genISN, genAdj, genObsVal),
				)
			}
		}
	}

	dailyMatches := 0
	dailyTotal := 0
	for dateKey, offLine := range offDaily {
		if genLine, ok := genDaily[dateKey]; ok {
			dailyTotal++

			if len(offLine) < 98 || len(genLine) < 98 {
				continue
			}

			offAvg, _ := strconv.Atoi(strings.TrimSpace(offLine[78:82]))
			genAvg, _ := strconv.Atoi(strings.TrimSpace(genLine[78:82]))

			offISN, _ := strconv.Atoi(strings.TrimSpace(offLine[88:92]))
			genISN, _ := strconv.Atoi(strings.TrimSpace(genLine[88:92]))

			offAdj, _ := strconv.ParseFloat(strings.TrimSpace(offLine[92:98]), 64)
			genAdj, _ := strconv.ParseFloat(strings.TrimSpace(genLine[92:98]), 64)

			diffAvg := math.Abs(float64(offAvg - genAvg))
			diffISN := math.Abs(float64(offISN - genISN))
			diffAdj := math.Abs(offAdj - genAdj)

			if diffAvg <= 1.0 && diffISN <= 2.0 && diffAdj <= 1.0 {
				dailyMatches++
			} else {
				discrepancies = append(discrepancies,
					fmt.Sprintf("PRED %s: CelesTrak=(AvgAp:%d, ISN:%d, AdjFlux:%.1f) Local=(AvgAp:%d, ISN:%d, AdjFlux:%.1f)",
						dateKey, offAvg, offISN, offAdj, genAvg, genISN, genAdj),
				)
			}
		}
	}

	obsRate := 0.0
	if totalChecked > 0 {
		obsRate = float64(matches) / float64(totalChecked)
	}

	predRate := 0.0
	if dailyTotal > 0 {
		predRate = float64(dailyMatches) / float64(dailyTotal)
	}

	c.log("\n--- VERIFICATION REPORT ---")
	c.log(fmt.Sprintf("Observed Section Compatibility: %d / %d matched (%.2f%%)", matches, totalChecked, obsRate*100))
	if dailyTotal > 0 {
		c.log(fmt.Sprintf("Daily Predictions Compatibility: %d / %d matched (%.2f%%)", dailyMatches, dailyTotal, predRate*100))
	}
	c.log(fmt.Sprintf("Total Discrepancies: %d", len(discrepancies)))

	return &VerificationResult{
		ObsMatchRate:  obsRate,
		PredMatchRate: predRate,
		Discrepancies: discrepancies,
	}, nil
}
