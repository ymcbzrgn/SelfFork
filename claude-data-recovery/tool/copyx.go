package main

import (
	"crypto/sha256"
	"encoding/hex"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// runCopy executes the plan, copying every non-skipped item. If a copy hits a
// FATAL condition (disk full / drive gone / write-protected) it stops the loop
// and marks the rest as skipped-aborted, instead of failing thousands of times.
func runCopy(cfg *Config, plan *Plan, pr *Progress) []Result {
	res := make([]Result, 0, len(plan.Items))
	aborted := false
	for i, it := range plan.Items {
		if aborted {
			res = append(res, Result{Item: it, Status: "skipped-aborted", OutRel: it.Rel})
			continue
		}
		pr.setCur(it.Src)
		if it.Action == "skip-secret" {
			res = append(res, Result{Item: it, Status: "skipped-secret", OutRel: it.Rel})
			continue
		}
		hash, status, fatal := copyItem(it, cfg, pr)
		if strings.HasPrefix(status, "error") {
			plan.addExcluded(it.Src, status)
		}
		res = append(res, Result{Item: it, Hash: hash, Status: status, OutRel: it.Rel})
		if fatal {
			aborted = true
			plan.logf("FATAL after %d items: %s — copy aborted", i+1, status)
			pr.setCur("ABORTED: " + status)
		}
	}
	return res
}

func copyItem(it Item, cfg *Config, pr *Progress) (hash, status string, fatal bool) {
	dst := longPath(filepath.Join(cfg.OutDir, it.Rel))
	srcPath := longPath(it.Src)
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		s, f := failStatus("mkdir", err)
		return "", s, f
	}

	// Redacted files are small JSON configs: read fully, scrub, write+flush.
	if it.Action == "redact" {
		data, err := os.ReadFile(srcPath)
		if err != nil {
			s, f := failStatus("read", err)
			return "", s, f
		}
		red, ok := redactJSON(data)
		if err := writeFileSync(dst, red, 0o600); err != nil {
			s, f := failStatus("write", err)
			return "", s, f
		}
		pr.add(int64(len(red)))
		sum := sha256.Sum256(red)
		if ok {
			return hex.EncodeToString(sum[:]), "redacted", false
		}
		return hex.EncodeToString(sum[:]), "copied(redact-noparse)", false
	}

	src, err := openWithRetry(srcPath, 4)
	if err != nil {
		s, f := failStatus("open", err)
		return "", s, f
	}
	defer src.Close()

	perm := os.FileMode(0o644)
	if it.Action == "quarantine" || it.Action == "copy-secret" {
		perm = 0o600
	}
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, perm)
	if err != nil {
		s, f := failStatus("create", err)
		return "", s, f
	}
	h := sha256.New()
	_, cerr := io.Copy(io.MultiWriter(out, h, pr.writer()), src)
	if cerr == nil {
		cerr = out.Sync() // flush to disk — durability on removable media
	}
	closeErr := out.Close()
	if cerr != nil {
		_ = os.Remove(dst) // drop the partial file
		s, f := failStatus("copy", cerr)
		return "", s, f
	}
	if closeErr != nil {
		s, f := failStatus("close", closeErr)
		return "", s, f
	}

	switch it.Action {
	case "quarantine":
		status = "quarantined"
	case "copy-secret":
		status = "copied-secret"
	default:
		status = "copied"
	}
	return hex.EncodeToString(h.Sum(nil)), status, false
}

// failStatus turns a copy error into a status string and flags whether it is
// FATAL (a whole-run stopper: disk full, drive gone, write-protected) so the
// loop can abort early instead of repeating the same failure thousands of times.
func failStatus(op string, err error) (status string, fatal bool) {
	switch classifyErr(err) {
	case "abort-diskfull":
		return "error: " + op + ": DISK FULL: " + err.Error(), true
	case "abort-readonly":
		return "error: " + op + ": WRITE-PROTECTED: " + err.Error(), true
	case "abort-notready":
		return "error: " + op + ": DRIVE NOT READY: " + err.Error(), true
	}
	return "error: " + op + ": " + err.Error(), false
}

// writeFileSync writes data and fsyncs before returning, so a redacted config
// is durably on disk (matters for removable drives that cache writes).
func writeFileSync(path string, data []byte, perm os.FileMode) error {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, perm)
	if err != nil {
		return err
	}
	if _, err := f.Write(data); err != nil {
		_ = f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		_ = f.Close()
		return err
	}
	return f.Close()
}

// openWithRetry retries ONLY transient sharing/lock violations (a file briefly
// held by another process). Non-transient errors fail fast — retrying an
// access-denied/not-found file thousands of times would waste minutes.
func openWithRetry(path string, tries int) (*os.File, error) {
	var f *os.File
	var err error
	for i := 0; i < tries; i++ {
		if f, err = os.Open(path); err == nil {
			return f, nil
		}
		if classifyErr(err) != "retry" {
			return nil, err
		}
		time.Sleep(200 * time.Millisecond)
	}
	return nil, err
}
