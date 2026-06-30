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

// runCopy executes the plan, copying every non-skipped item and returning a
// Result per item (including failures, which are also logged as excluded).
func runCopy(cfg *Config, plan *Plan, pr *Progress) []Result {
	res := make([]Result, 0, len(plan.Items))
	for _, it := range plan.Items {
		pr.setCur(it.Src)
		if it.Action == "skip-secret" {
			res = append(res, Result{Item: it, Status: "skipped-secret", OutRel: it.Rel})
			continue
		}
		hash, status := copyItem(it, cfg, pr)
		if strings.HasPrefix(status, "error") {
			plan.addExcluded(it.Src, status)
		}
		res = append(res, Result{Item: it, Hash: hash, Status: status, OutRel: it.Rel})
	}
	return res
}

func copyItem(it Item, cfg *Config, pr *Progress) (hash, status string) {
	dst := filepath.Join(cfg.OutDir, it.Rel)
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return "", "error: mkdir: " + err.Error()
	}

	// Redacted files are small JSON configs: read fully, scrub, write.
	if it.Action == "redact" {
		data, err := os.ReadFile(it.Src)
		if err != nil {
			return "", "error: read: " + err.Error()
		}
		red, ok := redactJSON(data)
		if err := os.WriteFile(dst, red, 0o600); err != nil {
			return "", "error: write: " + err.Error()
		}
		pr.add(int64(len(red)))
		sum := sha256.Sum256(red)
		if ok {
			return hex.EncodeToString(sum[:]), "redacted"
		}
		return hex.EncodeToString(sum[:]), "copied(redact-noparse)"
	}

	src, err := openWithRetry(it.Src, 3)
	if err != nil {
		return "", "error: open: " + err.Error()
	}
	defer src.Close()

	perm := os.FileMode(0o644)
	if it.Action == "quarantine" || it.Action == "copy-secret" {
		perm = 0o600
	}
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, perm)
	if err != nil {
		return "", "error: create: " + err.Error()
	}
	h := sha256.New()
	_, cerr := io.Copy(io.MultiWriter(out, h, pr.writer()), src)
	cerr2 := out.Close()
	if cerr != nil {
		return "", "error: copy: " + cerr.Error()
	}
	if cerr2 != nil {
		return "", "error: close: " + cerr2.Error()
	}

	switch it.Action {
	case "quarantine":
		status = "quarantined"
	case "copy-secret":
		status = "copied-secret"
	default:
		status = "copied"
	}
	return hex.EncodeToString(h.Sum(nil)), status
}

// openWithRetry retries a few times to tolerate briefly-locked files (e.g. a
// log being flushed). It does NOT use shadow copies or any forced-handle trick.
func openWithRetry(path string, tries int) (*os.File, error) {
	var f *os.File
	var err error
	for i := 0; i < tries; i++ {
		if f, err = os.Open(path); err == nil {
			return f, nil
		}
		time.Sleep(150 * time.Millisecond)
	}
	return nil, err
}
