package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
)

// gSilent mirrors cfg.Silent for abort(), which has no cfg in scope.
var gSilent bool

// preflight runs BEFORE the copy loop. It tells the user exactly where output
// will land, warns if that is an internal disk (not the USB they expect),
// proves the destination is writable, and checks there is enough free space —
// turning a 3000-file mid-run meltdown into one clear up-front message.
func preflight(cfg *Config, plan *Plan) {
	fmt.Println("  Pre-flight checks:")

	kind := driveKind(cfg.OutDir)
	fmt.Printf("    - Output: %s   (%s drive)\n", cfg.OutDir, kind)
	switch kind {
	case "fixed":
		fmt.Println("    ! WARNING: output is on a FIXED / INTERNAL drive, not a USB.")
		fmt.Println("      If you meant the flash drive: put the exe ON the USB, or pass")
		fmt.Println("      e.g.  ClaudeBackup.exe --out E:\\claude-backup")
	case "remote":
		fmt.Println("    ! WARNING: output is on a NETWORK drive — may be slow or unreliable.")
	case "cdrom":
		abort("output is on a read-only CD/DVD drive — choose another destination.")
	}

	// Writability probe — create the dir and round-trip a tiny file.
	if err := os.MkdirAll(longPath(cfg.OutDir), 0o755); err != nil {
		abort("cannot create the output folder:\n      " + err.Error())
	}
	probe := longPath(filepath.Join(cfg.OutDir, ".write-test"))
	if err := os.WriteFile(probe, []byte("ok"), 0o644); err != nil {
		abort("output folder is NOT writable:\n      " + err.Error() +
			"\n      (read-only media, no permission, or AV block — try another drive or run as Administrator)")
	}
	_ = os.Remove(probe)
	fmt.Println("    - Writable: yes")

	// Free-space gate.
	if free, ok := freeBytes(cfg.OutDir); ok {
		need := uint64(plan.TotalBytes)
		margin := need/20 + (64 << 20) // +5% +64 MB
		fmt.Printf("    - Space: need %s, free %s\n", human(plan.TotalBytes), human(int64(free)))
		if free < need+margin {
			if cfg.Force {
				fmt.Println("    ! Low space, continuing anyway (--force).")
			} else {
				abort(fmt.Sprintf("not enough space on the destination.\n      Need ~%s, only %s free. Free up space or use a bigger drive\n      (or pass --force to try anyway).",
					human(plan.TotalBytes), human(int64(free))))
			}
		}
	}
	fmt.Println()
}

// abort prints a clear failure and exits, keeping the window open (unless
// --silent) so the user can read it on a double-click run.
func abort(msg string) {
	fmt.Println("\n  X ABORTED: " + msg)
	if !gSilent {
		fmt.Print("\n  Press Enter to close… ")
		_, _ = bufio.NewReader(os.Stdin).ReadString('\n')
	}
	os.Exit(1)
}

// verifyOutput re-checks, after the run, that the manifest actually landed on
// disk — so a silently-lost or non-persisted backup can't masquerade as success.
func verifyOutput(cfg *Config) bool {
	if cfg.DryRun {
		return true
	}
	_, err := os.Stat(longPath(filepath.Join(cfg.OutDir, "MANIFEST.csv")))
	return err == nil
}
