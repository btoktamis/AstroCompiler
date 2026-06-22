package main

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/btoktamis/eop"
	"github.com/btoktamis/spaceweather"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// App struct manages application state and exposes Go methods to JS.
type App struct {
	ctx context.Context
}

// NewApp creates a new App application struct.
func NewApp() *App {
	return &App{}
}

// startup is called when the app starts.
func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
}

// LogMessage emits a log message event to the frontend.
func (a *App) LogMessage(category, msg string) {
	runtime.EventsEmit(a.ctx, "log", map[string]string{
		"category": category,
		"message":  msg,
	})
}

// CompileSpaceWeather runs the space weather compilation and writes the output file.
func (a *App) CompileSpaceWeather(offline bool, cacheDir, outPath, format string) (map[string]interface{}, error) {
	if cacheDir == "" {
		cacheDir = "./cache"
	}
	if outPath == "" {
		outPath = "./SW-All." + strings.ToLower(format)
	}

	a.LogMessage("spaceweather", "Initializing Space Weather Compiler...")
	compiler := &spaceweather.SpaceWeatherCompiler{
		CacheDir: cacheDir,
		LogCallback: func(msg string) {
			a.LogMessage("spaceweather", msg)
		},
	}

	result, err := compiler.Compile()
	if err != nil {
		a.LogMessage("spaceweather", fmt.Sprintf("Error compiling: %v", err))
		return nil, err
	}

	formatLower := strings.ToLower(format)
	if formatLower == "csv" {
		a.LogMessage("spaceweather", fmt.Sprintf("Saving CSV database to %s...", outPath))
		err = compiler.WriteToCSV(result, outPath)
	} else {
		a.LogMessage("spaceweather", fmt.Sprintf("Saving legacy TXT database to %s...", outPath))
		err = compiler.WriteToLegacyTXT(result, outPath)
	}

	if err != nil {
		a.LogMessage("spaceweather", fmt.Sprintf("Error saving file: %v", err))
		return nil, err
	}

	a.LogMessage("spaceweather", "Space Weather Compilation completed successfully!")

	// Perform verification
	var verifyRes interface{}
	if formatLower != "csv" {
		a.LogMessage("spaceweather", "Running compatibility verification with Celestrak...")
		v, err := compiler.VerifyWithCelestrak(outPath)
		if err == nil {
			verifyRes = v
		} else {
			a.LogMessage("spaceweather", fmt.Sprintf("Verification failed: %v", err))
		}
	}

	return map[string]interface{}{
		"success":        true,
		"observed_count": len(result.Observed),
		"daily_count":    len(result.Daily),
		"monthly_count":  len(result.Monthly),
		"observed":       result.Observed,
		"daily":          result.Daily,
		"monthly":        result.Monthly,
		"verification":   verifyRes,
	}, nil
}

// CompileEOP runs EOP compilation and writes the output file.
func (a *App) CompileEOP(offline bool, cacheDir, outPath, format string) (map[string]interface{}, error) {
	if cacheDir == "" {
		cacheDir = "./cache"
	}
	if outPath == "" {
		outPath = "./EOP-All." + strings.ToLower(format)
	}

	a.LogMessage("eop", "Initializing Earth Orientation Parameters Compiler...")
	compiler := &eop.EOPCompiler{
		CacheDir: cacheDir,
		LogCallback: func(msg string) {
			a.LogMessage("eop", msg)
		},
	}

	result, err := compiler.Compile(offline)
	if err != nil {
		a.LogMessage("eop", fmt.Sprintf("Error compiling EOP: %v", err))
		return nil, err
	}

	formatLower := strings.ToLower(format)
	if formatLower == "csv" {
		a.LogMessage("eop", fmt.Sprintf("Saving CSV database to %s...", outPath))
		err = compiler.WriteToCSV(result, outPath)
	} else {
		a.LogMessage("eop", fmt.Sprintf("Saving legacy TXT database to %s...", outPath))
		err = compiler.WriteToLegacyTXT(result, outPath, true)
	}

	if err != nil {
		a.LogMessage("eop", fmt.Sprintf("Error saving EOP file: %v", err))
		return nil, err
	}

	a.LogMessage("eop", "EOP Compilation completed successfully!")

	// Perform verification
	var verifyRes interface{}
	if formatLower != "csv" {
		a.LogMessage("eop", "Running compatibility verification with Celestrak...")
		v, err := compiler.VerifyWithCelestrak(outPath)
		if err == nil {
			verifyRes = v
		} else {
			a.LogMessage("eop", fmt.Sprintf("Verification failed: %v", err))
		}
	}

	return map[string]interface{}{
		"success":        true,
		"observed_count": len(result.Observed),
		"predicted_count": len(result.Predicted),
		"observed":       result.Observed,
		"predicted":      result.Predicted,
		"verification":   verifyRes,
	}, nil
}

// LoadSpaceWeatherCSV loads compiled Space Weather from a CSV file.
func (a *App) LoadSpaceWeatherCSV(filePath string) ([]spaceweather.Record, error) {
	f, err := os.Open(filePath)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	reader := csv.NewReader(f)
	records, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}

	if len(records) < 2 {
		return nil, fmt.Errorf("empty CSV file")
	}

	// Map headers to indices
	headerMap := make(map[string]int)
	for i, h := range records[0] {
		headerMap[h] = i
	}

	var result []spaceweather.Record
	for idx, row := range records[1:] {
		// Read values
		dateVal := row[headerMap["DATE"]]
		bsrnVal, _ := strconv.Atoi(row[headerMap["BSRN"]])
		ndVal, _ := strconv.Atoi(row[headerMap["ND"]])
		apAvgVal, _ := strconv.Atoi(row[headerMap["AP_AVG"]])
		isnVal, _ := strconv.Atoi(row[headerMap["ISN"]])
		f107Obs, _ := strconv.ParseFloat(row[headerMap["F107_OBS"]], 64)
		f107Adj, _ := strconv.ParseFloat(row[headerMap["F107_ADJ"]], 64)
		f107ObsCtr, _ := strconv.ParseFloat(row[headerMap["F107_OBS_CTR81"]], 64)
		f107ObsLst, _ := strconv.ParseFloat(row[headerMap["F107_OBS_LST81"]], 64)
		f107AdjCtr, _ := strconv.ParseFloat(row[headerMap["F107_ADJ_CTR81"]], 64)
		f107AdjLst, _ := strconv.ParseFloat(row[headerMap["F107_ADJ_LST81"]], 64)
		qFlag, _ := strconv.Atoi(row[headerMap["Q_FLAG"]])
		dType := row[headerMap["DATA_TYPE"]]

		// Parse date fields
		var y, m, d int
		dateParts := strings.Split(dateVal, "-")
		if len(dateParts) == 3 {
			y, _ = strconv.Atoi(dateParts[0])
			m, _ = strconv.Atoi(dateParts[1])
			d, _ = strconv.Atoi(dateParts[2])
		}

		kpVals := make([]int, 8)
		apVals := make([]int, 8)
		if dType != "M" {
			for i := 1; i <= 8; i++ {
				kpKey := fmt.Sprintf("KP%d", i)
				apKey := fmt.Sprintf("AP%d", i)
				if colIdx, ok := headerMap[kpKey]; ok && row[colIdx] != "" {
					v, _ := strconv.Atoi(row[colIdx])
					kpVals[i-1] = v
				} else {
					kpVals[i-1] = -1
				}
				if colIdx, ok := headerMap[apKey]; ok && row[colIdx] != "" {
					v, _ := strconv.Atoi(row[colIdx])
					apVals[i-1] = v
				}
			}
		}

		result = append(result, spaceweather.Record{
			Date:       dateVal,
			Year:       y,
			Month:      m,
			Day:        d,
			BSRN:       bsrnVal,
			ND:         ndVal,
			KpVals:     kpVals,
			ApVals:     apVals,
			ApAvg:      apAvgVal,
			ISN:        isnVal,
			F107Obs:    f107Obs,
			F107Adj:    f107Adj,
			F107ObsCtr: f107ObsCtr,
			F107ObsLst: f107ObsLst,
			F107AdjCtr: f107AdjCtr,
			F107AdjLst: f107AdjLst,
			QFlag:      qFlag,
			Source:     dType,
		})
		_ = idx
	}

	return result, nil
}

// LoadEOPCSV loads compiled EOP data from a CSV file.
func (a *App) LoadEOPCSV(filePath string) ([]eop.EOPRecord, error) {
	f, err := os.Open(filePath)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	reader := csv.NewReader(f)
	records, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}

	if len(records) < 2 {
		return nil, fmt.Errorf("empty EOP CSV file")
	}

	headerMap := make(map[string]int)
	for i, h := range records[0] {
		headerMap[h] = i
	}

	var result []eop.EOPRecord
	for _, row := range records[1:] {
		dateVal := row[headerMap["DATE"]]
		mjd, _ := strconv.Atoi(row[headerMap["MJD"]])
		x, _ := strconv.ParseFloat(row[headerMap["X"]], 64)
		y, _ := strconv.ParseFloat(row[headerMap["Y"]], 64)
		ut1, _ := strconv.ParseFloat(row[headerMap["UT1-UTC"]], 64)
		lod, _ := strconv.ParseFloat(row[headerMap["LOD"]], 64)
		dpsi, _ := strconv.ParseFloat(row[headerMap["DPSI"]], 64)
		deps, _ := strconv.ParseFloat(row[headerMap["DEPS"]], 64)
		dx, _ := strconv.ParseFloat(row[headerMap["DX"]], 64)
		dy, _ := strconv.ParseFloat(row[headerMap["DY"]], 64)
		dat, _ := strconv.Atoi(row[headerMap["DAT"]])
		dType := row[headerMap["DATA_TYPE"]]

		var yy, mm, dd int
		dateParts := strings.Split(dateVal, "-")
		if len(dateParts) == 3 {
			yy, _ = strconv.Atoi(dateParts[0])
			mm, _ = strconv.Atoi(dateParts[1])
			dd, _ = strconv.Atoi(dateParts[2])
		}

		result = append(result, eop.EOPRecord{
			Year:   yy,
			Month:  mm,
			Day:    dd,
			MJD:    mjd,
			X:      x,
			Y:      y,
			UT1UTC: ut1,
			LOD:    lod,
			DPsi:   dpsi,
			DEps:   deps,
			DX:     dx,
			DY:     dy,
			DAT:    dat,
			Type:   dType,
		})
	}
	return result, nil
}

type AppConfig struct {
	SpaceWeatherOutputPath string `json:"sw_output_path"`
	SpaceWeatherFormat     string `json:"sw_format"`
	SpaceWeatherCacheDir   string `json:"sw_cache_dir"`
	EOPOutputPath          string `json:"eop_output_path"`
	EOPFormat              string `json:"eop_format"`
	EOPCacheDir            string `json:"eop_cache_dir"`
	EOPCompileMode         string `json:"eop_compile_mode"`
}

func getConfigPath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return "./astro_config.json"
	}
	return filepath.Join(home, ".astro_config.json")
}

// LoadConfig loads the saved settings from the user's config file.
func (a *App) LoadConfig() (AppConfig, error) {
	var cfg AppConfig
	path := getConfigPath()
	data, err := os.ReadFile(path)
	if err != nil {
		// Return empty default config
		return cfg, nil
	}
	err = json.Unmarshal(data, &cfg)
	if err != nil {
		return cfg, err
	}
	return cfg, nil
}

// SaveConfig saves the configuration to the user's config file.
func (a *App) SaveConfig(cfg AppConfig) error {
	path := getConfigPath()
	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

// SelectSaveFile opens a save file dialog to choose output file path.
func (a *App) SelectSaveFile(title, defaultFilename, pattern string) (string, error) {
	return runtime.SaveFileDialog(a.ctx, runtime.SaveDialogOptions{
		Title:           title,
		DefaultFilename: defaultFilename,
		Filters: []runtime.FileFilter{
			{
				DisplayName: "Astro Data Files",
				Pattern:     pattern,
			},
		},
	})
}
