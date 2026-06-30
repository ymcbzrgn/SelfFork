package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// writeReports writes the manifest, checksums, run log, excluded list, summary
// and a human README into the output dir, and returns the rollup Summary.
func writeReports(cfg *Config, plan *Plan, results []Result, host string, start time.Time) Summary {
	if err := os.MkdirAll(longPath(cfg.OutDir), 0o755); err != nil {
		fmt.Printf("  ⚠ could not create output dir %s: %v\n", cfg.OutDir, err)
	}
	sum := Summary{ByKind: map[string]int{}, ErrorReasons: map[string]int{}, OutDir: cfg.OutDir, Host: host, Excluded: len(plan.Excluded)}

	if err := writeManifestCSV(longPath(filepath.Join(cfg.OutDir, "MANIFEST.csv")), results); err != nil {
		fmt.Printf("  ⚠ MANIFEST.csv could not be written to %s: %v\n", cfg.OutDir, err)
	}

	if b, err := json.MarshalIndent(results, "", "  "); err == nil {
		_ = os.WriteFile(longPath(filepath.Join(cfg.OutDir, "MANIFEST.json")), b, 0o644)
	}

	if !cfg.DryRun {
		var sb strings.Builder
		for _, r := range results {
			if r.Hash != "" {
				sb.WriteString(r.Hash + " *" + r.OutRel + "\n")
			}
		}
		_ = os.WriteFile(longPath(filepath.Join(cfg.OutDir, "CHECKSUMS.sha256")), []byte(sb.String()), 0o644)
	}

	for _, r := range results {
		switch {
		case strings.HasPrefix(r.Status, "error"):
			sum.Errors++
			sum.ErrorReasons[normalizeErr(r.Status)]++
			if len(sum.ErrorSamples) < 5 {
				sum.ErrorSamples = append(sum.ErrorSamples, r.Status)
			}
		case r.Status == "skipped-secret" || r.Status == "planned-skip-secret":
			sum.SkippedSecret++
		case r.Status == "skipped-aborted":
			sum.Aborted++
		case r.Status == "quarantined":
			sum.Quarantined++
			countCollected(&sum, r)
		case r.Status == "redacted" || strings.HasPrefix(r.Status, "copied(redact"):
			sum.Redacted++
			countCollected(&sum, r)
		default: // copied, copied-secret, planned
			countCollected(&sum, r)
		}
	}
	sum.Elapsed = fmtDur(time.Since(start).Seconds())

	_ = os.WriteFile(longPath(filepath.Join(cfg.OutDir, "EXCLUDED.txt")), []byte(strings.Join(plan.Excluded, "\n")+"\n"), 0o644)
	writeRunLog(cfg, plan, sum, host, start)
	writeSummaryTxt(cfg, sum)
	writeReadme(cfg, host, start)
	mirrorToTemp(host, start, sum, plan) // local copy that survives USB removal
	return sum
}

// mirrorToTemp writes a compact run log to the LOCAL temp dir, so evidence of
// what happened (and why files failed) survives even if the USB is pulled or
// its output is lost.
func mirrorToTemp(host string, start time.Time, sum Summary, plan *Plan) {
	dir := filepath.Join(os.TempDir(), "claude-backup-logs")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return
	}
	var b strings.Builder
	b.WriteString("Claude backup — local run-log mirror (survives USB removal)\n")
	b.WriteString("Host:   " + host + "\n")
	b.WriteString("Start:  " + start.Format(time.RFC3339) + "\n")
	b.WriteString("Output: " + sum.OutDir + "\n")
	b.WriteString(fmt.Sprintf("Files: %d  Bytes: %s  Errors: %d  Aborted: %d  Excluded: %d\n",
		sum.Files, human(sum.Bytes), sum.Errors, sum.Aborted, sum.Excluded))
	if sum.Errors > 0 {
		b.WriteString("\nWhy files failed:\n")
		for _, kv := range topReasons(sum.ErrorReasons, 30) {
			b.WriteString(fmt.Sprintf("  %6d  %s\n", kv.n, kv.reason))
		}
	}
	b.WriteString("\nExcluded (first 300):\n")
	for i, l := range plan.Excluded {
		if i >= 300 {
			b.WriteString(fmt.Sprintf("  …and %d more\n", len(plan.Excluded)-300))
			break
		}
		b.WriteString("  " + l + "\n")
	}
	name := filepath.Join(dir, host+"-"+start.Format("20060102-150405")+".log")
	_ = os.WriteFile(name, []byte(b.String()), 0o644)
}

func countCollected(sum *Summary, r Result) {
	sum.Files++
	sum.Bytes += r.Size
	sum.ByKind[r.Kind]++
}

func writeManifestCSV(path string, results []Result) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	w := csv.NewWriter(f)
	_ = w.Write([]string{"OriginalPath", "Size", "SHA256", "Kind", "Action", "Status", "OutputRel", "Secret"})
	for _, r := range results {
		_ = w.Write([]string{
			r.Src,
			fmt.Sprintf("%d", r.Size),
			r.Hash,
			r.Kind,
			r.Action,
			r.Status,
			r.OutRel,
			fmt.Sprintf("%t", r.Secret),
		})
	}
	w.Flush()
	if err := w.Error(); err != nil {
		f.Close()
		return err
	}
	return f.Close()
}

func writeRunLog(cfg *Config, plan *Plan, sum Summary, host string, start time.Time) {
	var b strings.Builder
	b.WriteString("Claude Code Data Recovery — RUN LOG\n")
	b.WriteString("==================================\n")
	b.WriteString("Start:  " + start.Format(time.RFC3339) + "\n")
	b.WriteString("Host:   " + host + "\n")
	b.WriteString(fmt.Sprintf("Mode:   secrets=%s lean=%t exhaustive=%t allUsers=%t dryRun=%t\n",
		cfg.Secrets, cfg.Lean, cfg.Exhaustive, cfg.AllUsers, cfg.DryRun))
	b.WriteString("Output: " + cfg.OutDir + "\n\n")
	for _, l := range plan.Log {
		b.WriteString("  " + l + "\n")
	}
	b.WriteString(fmt.Sprintf("\nFiles: %d   Bytes: %s   Quarantined: %d   Redacted: %d   SkippedSecret: %d   Errors: %d   Excluded: %d\n",
		sum.Files, human(sum.Bytes), sum.Quarantined, sum.Redacted, sum.SkippedSecret, sum.Errors, sum.Excluded))
	b.WriteString("Elapsed: " + sum.Elapsed + "\n")
	_ = os.WriteFile(longPath(filepath.Join(cfg.OutDir, "RUN_LOG.txt")), []byte(b.String()), 0o644)
}

func writeSummaryTxt(cfg *Config, sum Summary) {
	var b strings.Builder
	b.WriteString("SUMMARY\n=======\n")
	b.WriteString(fmt.Sprintf("Host:            %s\n", sum.Host))
	b.WriteString(fmt.Sprintf("Files collected: %d\n", sum.Files))
	b.WriteString(fmt.Sprintf("Total bytes:     %s\n", human(sum.Bytes)))
	b.WriteString(fmt.Sprintf("Quarantined:     %d\n", sum.Quarantined))
	b.WriteString(fmt.Sprintf("Redacted:        %d\n", sum.Redacted))
	b.WriteString(fmt.Sprintf("Skipped secret:  %d\n", sum.SkippedSecret))
	b.WriteString(fmt.Sprintf("Aborted (unrun): %d\n", sum.Aborted))
	b.WriteString(fmt.Sprintf("Errors:          %d\n", sum.Errors))
	b.WriteString(fmt.Sprintf("Excluded:        %d\n", sum.Excluded))
	b.WriteString("\nBy kind:\n")
	for k, v := range sum.ByKind {
		b.WriteString(fmt.Sprintf("  %-20s %d\n", k, v))
	}
	if sum.Errors > 0 {
		b.WriteString("\nError reasons (why files failed):\n")
		for _, kv := range topReasons(sum.ErrorReasons, 20) {
			b.WriteString(fmt.Sprintf("  %6d  %s\n", kv.n, kv.reason))
		}
	}
	_ = os.WriteFile(longPath(filepath.Join(cfg.OutDir, "SUMMARY.txt")), []byte(b.String()), 0o644)
}

func writeReadme(cfg *Config, host string, start time.Time) {
	var b strings.Builder
	b.WriteString("CLAUDE CODE DATA BACKUP\n")
	b.WriteString("=======================\n\n")
	b.WriteString("This folder is an OVERT backup of Claude Code (terminal CLI) data,\n")
	b.WriteString("created by the SelfFork Claude Data Recovery Kit.\n\n")
	b.WriteString("Host:    " + host + "\n")
	b.WriteString("When:    " + start.Format(time.RFC3339) + "\n")
	b.WriteString("Secrets: " + cfg.Secrets + "\n\n")
	b.WriteString("Layout:\n")
	b.WriteString("  <host>/<user>/global/      ~/.claude, ~/.claude.json*, ~/.claude-mem\n")
	b.WriteString("  <host>/<user>/by-drive/    project-level .claude / CLAUDE.md / .mcp.json\n")
	b.WriteString("  <host>/<user>/__SECRETS__/ quarantined live credentials (safe mode)\n\n")
	b.WriteString("Verify with: sha256sum -c CHECKSUMS.sha256\n\n")
	b.WriteString("WARNING: contents may include conversation transcripts, pasted secrets\n")
	b.WriteString("and live OAuth tokens. Handle as confidential. Rotate any captured\n")
	b.WriteString("credentials after use. Only retain with proper authorization.\n")
	_ = os.WriteFile(longPath(filepath.Join(cfg.OutDir, "README.txt")), []byte(b.String()), 0o644)
}
