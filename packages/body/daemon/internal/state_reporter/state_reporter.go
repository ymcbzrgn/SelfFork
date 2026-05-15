// Package state_reporter streams M3-format CLI snapper state to the orchestrator.
//
// Polls ``~/.selffork/cli-state/<cli>.json`` files at a configurable cadence
// (default 1 s) and posts deltas to ``/api/fleet/state``. The home cockpit's
// Run tab merges these into the unified Run timeline.
package state_reporter

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Reporter configuration.
type Reporter struct {
	OrchestratorURL string
	MachineID       string
	SnapperRoot     string
	Interval        time.Duration
	Client          *http.Client

	lastHashes map[string]string
}

type frame struct {
	MachineID string          `json:"machine_id"`
	CLI       string          `json:"cli"`
	State     json.RawMessage `json:"state"`
	SentAt    string          `json:"sent_at"`
}

// Run drives the reporter loop until ctx is cancelled.
func (r *Reporter) Run(ctx context.Context) error {
	if r.Interval <= 0 {
		r.Interval = time.Second
	}
	if r.SnapperRoot == "" {
		home, _ := os.UserHomeDir()
		r.SnapperRoot = filepath.Join(home, ".selffork", "cli-state")
	}
	if r.Client == nil {
		r.Client = &http.Client{Timeout: 10 * time.Second}
	}
	r.lastHashes = make(map[string]string)

	timer := time.NewTimer(r.Interval)
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-timer.C:
		}
		_ = r.poll(ctx)
		timer.Reset(r.Interval)
	}
}

// poll reads each .json under SnapperRoot and posts changed frames.
func (r *Reporter) poll(ctx context.Context) error {
	entries, err := os.ReadDir(r.SnapperRoot)
	if err != nil {
		return err
	}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		path := filepath.Join(r.SnapperRoot, e.Name())
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		hash := hashBytes(data)
		cli := strings.TrimSuffix(e.Name(), ".json")
		if r.lastHashes[cli] == hash {
			continue
		}
		f := frame{
			MachineID: r.MachineID,
			CLI:       cli,
			State:     data,
			SentAt:    time.Now().UTC().Format(time.RFC3339),
		}
		body, err := json.Marshal(f)
		if err != nil {
			continue
		}
		req, err := http.NewRequestWithContext(
			ctx, http.MethodPost,
			r.OrchestratorURL+"/api/fleet/state",
			bytes.NewReader(body),
		)
		if err != nil {
			continue
		}
		req.Header.Set("Content-Type", "application/json")
		resp, err := r.Client.Do(req)
		if err != nil {
			continue
		}
		_ = resp.Body.Close()
		if resp.StatusCode < 400 {
			r.lastHashes[cli] = hash
		}
	}
	return nil
}

func hashBytes(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}
