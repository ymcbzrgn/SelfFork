// Command claude-recovery collects all Claude Code (terminal CLI) data from a
// machine onto a portable drive: the per-user global store (~/.claude,
// ~/.claude.json, ~/.claude-mem) plus project-level artifacts (.claude/,
// CLAUDE.md, .mcp.json) scattered across every fixed drive.
//
// It is an OVERT backup/handover tool. It writes a manifest, checksums and a
// run log; it does not hide, obfuscate or evade. Only run it on machines you
// are authorized to back up. See ../README.md for the full design and the
// authorization/ethics note.
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const (
	appName    = "Claude Code Data Recovery Kit"
	appVersion = "v0.3"
)

// Config holds the resolved run options.
type Config struct {
	OutDir           string
	Roots            []string // override sweep volumes (testing); empty = all drives
	DryRun           bool
	Secrets          string // safe | redact-only | full
	Lean             bool
	Exhaustive       bool
	AllUsers         bool
	NoElevate        bool
	IncludeRemovable bool
	Zip              bool
	Silent           bool
	Force            bool
}

// Summary is the end-of-run rollup shown to the user and written to disk.
type Summary struct {
	Files         int
	Bytes         int64
	Redacted      int
	Quarantined   int
	SkippedSecret int
	Aborted       int
	Errors        int
	Excluded      int
	ByKind        map[string]int
	ErrorReasons  map[string]int
	ErrorSamples  []string
	OutDir        string
	Host          string
	Elapsed       string
}

func main() {
	cfg := parseFlags()
	gSilent = cfg.Silent

	// To read OTHER users' profiles we need Administrator. Re-launch elevated via
	// a UAC prompt (overt, user-consented). Not for dry-runs; --no-elevate skips.
	if cfg.AllUsers && !cfg.DryRun && !cfg.NoElevate && !isElevated() {
		fmt.Println("\n  Requesting Administrator (UAC) to read all user profiles…")
		if err := relaunchElevated(); err == nil {
			os.Exit(0) // the elevated instance takes over
		}
		fmt.Println("  Elevation unavailable; continuing with currently-accessible profiles only.")
	}

	start := time.Now()
	host, _ := os.Hostname()
	if host == "" {
		host = "UNKNOWN-HOST"
	}

	printBanner(cfg, host)

	fmt.Println("  [1/3] Discovering Claude data (global store + project sweep)…")
	plan := buildPlan(cfg, host)
	fmt.Printf("        found %d files · %s to copy · %d entries skipped/secret-excluded\n\n",
		len(plan.Items), human(plan.TotalBytes), len(plan.Excluded))

	var results []Result
	if cfg.DryRun {
		fmt.Println("  [2/3] DRY-RUN — planning only, copying nothing.")
		results = planResults(plan)
	} else {
		preflight(cfg, plan) // aborts up-front on no-space / not-writable
		fmt.Printf("  [2/3] Copying to %s\n", cfg.OutDir)
		pr := newProgress(plan.TotalBytes)
		pr.run()
		results = runCopy(cfg, plan, pr)
		pr.finish()
	}

	fmt.Println("  [3/3] Writing manifest, checksums and run log…")
	sum := writeReports(cfg, plan, results, host, start)

	printSummary(sum, cfg)

	if !cfg.DryRun {
		if verifyOutput(cfg) {
			fmt.Printf("  ✓ Verified on disk: %s\n", cfg.OutDir)
		} else {
			fmt.Printf("  ✗ WARNING: manifest NOT found at %s after the run.\n", cfg.OutDir)
			fmt.Println("    Output may not have persisted (drive removed early? writes blocked?).")
			fmt.Println("    A local copy of this run's log is in your TEMP folder (claude-backup-logs).")
		}
	}
	waitForKey(cfg)
}

func parseFlags() *Config {
	cfg := &Config{}
	flag.StringVar(&cfg.OutDir, "out", "", "output root (default: <exe dir>\\claude-backup)")
	flag.BoolVar(&cfg.DryRun, "dry-run", false, "discover & plan only; copy nothing")
	flag.StringVar(&cfg.Secrets, "secrets", "safe", "secrets mode: safe | redact-only | full")
	flag.BoolVar(&cfg.Lean, "lean", false, "skip rebuildable caches (.claude/plugins, .claude-mem/chroma, logs)")
	flag.BoolVar(&cfg.Exhaustive, "exhaustive", false, "do not prune noise dirs during the drive sweep")
	flag.BoolVar(&cfg.AllUsers, "all-users", true, "scan all user profiles (default; needs Administrator for other users)")
	flag.BoolVar(&cfg.NoElevate, "no-elevate", false, "do not auto-request Administrator (UAC)")
	flag.BoolVar(&cfg.IncludeRemovable, "include-removable", false, "also sweep removable drives")
	flag.BoolVar(&cfg.Zip, "zip", false, "(not implemented yet) zip the result")
	flag.BoolVar(&cfg.Silent, "silent", false, "do not wait for a keypress at the end")
	flag.BoolVar(&cfg.Force, "force", false, "skip the pre-flight free-space gate (copy even if space looks short)")
	quick := flag.Bool("quick", false, "fast path: current user only, no elevation, pruned")
	everything := flag.Bool("everything", false, "complete machine sweep: all users + exhaustive + removable drives")
	var roots string
	flag.StringVar(&roots, "sweep-root", "", "comma-separated roots to sweep instead of all drives (testing)")
	showVer := flag.Bool("version", false, "print version and exit")
	flag.Parse()

	if *showVer {
		fmt.Println(appName, appVersion)
		os.Exit(0)
	}
	if *everything {
		cfg.AllUsers = true
		cfg.Exhaustive = true
		cfg.IncludeRemovable = true
	}
	if *quick {
		cfg.AllUsers = false
		cfg.NoElevate = true
	}
	switch cfg.Secrets {
	case "safe", "redact-only", "full":
	default:
		fmt.Fprintln(os.Stderr, "invalid --secrets (want safe|redact-only|full):", cfg.Secrets)
		os.Exit(2)
	}
	if roots != "" {
		for _, r := range strings.Split(roots, ",") {
			if r = strings.TrimSpace(r); r != "" {
				cfg.Roots = append(cfg.Roots, r)
			}
		}
	}
	if cfg.OutDir == "" {
		cfg.OutDir = defaultOutDir()
	}
	abs, err := filepath.Abs(cfg.OutDir)
	if err == nil {
		cfg.OutDir = abs
	}
	if cfg.Zip {
		fmt.Println("  (note: --zip is not implemented yet; producing a raw tree)")
	}
	return cfg
}

// defaultOutDir places the backup NEXT TO THE EXE — what people expect: run it
// from wherever (incl. deep inside a folder on the USB) and a claude-backup\
// folder appears right there. Deep locations are safe: copyItem forces the
// \\?\ extended-length form so we never hit the legacy 260-char path limit.
func defaultOutDir() string {
	if exe, err := os.Executable(); err == nil {
		return filepath.Join(filepath.Dir(exe), "claude-backup")
	}
	return filepath.Join(".", "claude-backup")
}

func printBanner(cfg *Config, host string) {
	fmt.Println()
	fmt.Println("  ==============================================================")
	fmt.Printf("   %s  %s   (read-only source · overt)\n", appName, appVersion)
	fmt.Println("  ==============================================================")
	mode := "secrets=" + cfg.Secrets
	if cfg.DryRun {
		mode += " · DRY-RUN"
	}
	if cfg.Lean {
		mode += " · lean"
	}
	if cfg.Exhaustive {
		mode += " · exhaustive"
	}
	if cfg.AllUsers {
		mode += " · all-users"
	}
	fmt.Printf("   Host: %s   Mode: %s\n", host, mode)
	fmt.Printf("   Out:  %s\n\n", cfg.OutDir)
}

func printSummary(s Summary, cfg *Config) {
	fmt.Println(" ──────────────────────────────────────────────────────────────")
	if cfg.DryRun {
		fmt.Printf("  DRY-RUN complete    planned: %d files · %s\n", s.Files, human(s.Bytes))
	} else {
		fmt.Printf("  DONE in %s    %d files · %s · %s\n", s.Elapsed, s.Files, human(s.Bytes), errStr(s.Errors))
	}
	if s.Quarantined > 0 || s.Redacted > 0 || s.SkippedSecret > 0 {
		fmt.Printf("  Secrets: %d quarantined · %d redacted · %d skipped\n", s.Quarantined, s.Redacted, s.SkippedSecret)
	}
	if s.Aborted > 0 {
		fmt.Printf("  ⛔ Copy ABORTED early (disk full / drive lost / write-protected): %d items not attempted.\n", s.Aborted)
	}
	if s.Errors > 0 {
		fmt.Printf("  ⚠ WHY %d failed (top reasons):\n", s.Errors)
		for _, kv := range topReasons(s.ErrorReasons, 6) {
			fmt.Printf("     %5d × %s\n", kv.n, kv.reason)
		}
		if len(s.ErrorSamples) > 0 {
			fmt.Println("  Example failures:")
			for _, e := range s.ErrorSamples {
				fmt.Println("     " + shorten(e, 110))
			}
		}
		fmt.Println("  Full list in EXCLUDED.txt.")
	}
	fmt.Printf("  Output:   %s\n", cfg.OutDir)
	fmt.Printf("  Manifest: MANIFEST.csv / .json   Verify: CHECKSUMS.sha256\n")
	fmt.Printf("  Skipped:  %d entries (see EXCLUDED.txt)\n", s.Excluded)
	fmt.Println(" ──────────────────────────────────────────────────────────────")
}

func errStr(n int) string {
	if n == 0 {
		return "0 errors"
	}
	return fmt.Sprintf("%d errors", n)
}

func waitForKey(cfg *Config) {
	if cfg.Silent {
		return
	}
	fmt.Print("\n  Press Enter to close… ")
	_, _ = bufio.NewReader(os.Stdin).ReadString('\n')
}

// ---- small shared helpers -------------------------------------------------

func human(b int64) string {
	const u = 1024.0
	f := float64(b)
	switch {
	case f >= u*u*u:
		return fmt.Sprintf("%.2f GB", f/(u*u*u))
	case f >= u*u:
		return fmt.Sprintf("%.1f MB", f/(u*u))
	case f >= u:
		return fmt.Sprintf("%.1f KB", f/u)
	default:
		return fmt.Sprintf("%d B", b)
	}
}

func shorten(s string, n int) string {
	if n <= 3 || len(s) <= n {
		return s
	}
	return "..." + s[len(s)-(n-3):]
}

func fmtDur(sec float64) string {
	if sec != sec || sec < 0 { // NaN or negative
		return "--:--"
	}
	s := int(sec)
	return fmt.Sprintf("%02d:%02d", s/60, s%60)
}

func keyPath(p string) string {
	return strings.ToLower(filepath.Clean(p))
}

type reasonCount struct {
	reason string
	n      int
}

func topReasons(m map[string]int, k int) []reasonCount {
	out := make([]reasonCount, 0, len(m))
	for r, n := range m {
		out = append(out, reasonCount{r, n})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].n > out[j].n })
	if len(out) > k {
		out = out[:k]
	}
	return out
}

// normalizeErr collapses a per-file error string to a path-independent reason
// so failures can be tallied, e.g.
// "error: open: open C:\x: Access is denied." -> "open: Access is denied."
func normalizeErr(s string) string {
	op := ""
	if parts := strings.SplitN(s, ": ", 3); len(parts) >= 2 {
		op = parts[1]
	}
	tail := s
	if i := strings.LastIndex(s, ": "); i >= 0 {
		tail = s[i+2:]
	}
	return op + ": " + tail
}

func sameOrUnder(path, base string) bool {
	if base == "" {
		return false
	}
	p := keyPath(path)
	b := keyPath(base)
	return p == b || strings.HasPrefix(p, b+string(filepath.Separator))
}
