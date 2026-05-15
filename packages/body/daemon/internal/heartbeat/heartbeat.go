// Package heartbeat keeps the orchestrator informed of daemon liveness.
//
// Posts ``{machine_id, location_tier, version, latency_self_ms}`` payloads to
// the orchestrator on a fixed cadence (default 15s) and applies an
// exponential backoff (1s → 2s → 5s → 15s → 30s → 60s, max) on failure.
package heartbeat

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// Heartbeat configuration. ``Run`` blocks until ctx is cancelled.
type Heartbeat struct {
	OrchestratorURL string
	MachineID       string
	LocationTier    string
	Version         string
	Interval        time.Duration

	// Allow injecting a fake client in tests.
	Client *http.Client
}

type heartbeatPayload struct {
	MachineID     string `json:"machine_id"`
	LocationTier  string `json:"location_tier"`
	Version       string `json:"version"`
	LatencySelfMS int64  `json:"latency_self_ms"`
	SentAt        string `json:"sent_at"`
}

// NextBackoff returns the next backoff for the given previous one.
func NextBackoff(previous time.Duration) time.Duration {
	steps := []time.Duration{
		time.Second,
		2 * time.Second,
		5 * time.Second,
		15 * time.Second,
		30 * time.Second,
		60 * time.Second,
	}
	if previous == 0 {
		return steps[0]
	}
	for _, step := range steps {
		if step > previous {
			return step
		}
	}
	return steps[len(steps)-1]
}

// Run drives the heartbeat loop until ctx is cancelled.
func (h *Heartbeat) Run(ctx context.Context) error {
	if h.Interval <= 0 {
		h.Interval = 15 * time.Second
	}
	client := h.Client
	if client == nil {
		client = &http.Client{Timeout: 10 * time.Second}
	}
	var backoff time.Duration

	for {
		select {
		case <-ctx.Done():
			return nil
		default:
		}

		start := time.Now()
		err := h.send(ctx, client)
		if err != nil {
			backoff = NextBackoff(backoff)
			if !sleep(ctx, backoff) {
				return nil
			}
			continue
		}
		backoff = 0
		// Hold approximately Interval between successful sends, accounting
		// for the latency of the request itself.
		spent := time.Since(start)
		wait := h.Interval - spent
		if wait < 0 {
			wait = 0
		}
		if !sleep(ctx, wait) {
			return nil
		}
	}
}

func (h *Heartbeat) send(ctx context.Context, client *http.Client) error {
	payload := heartbeatPayload{
		MachineID:    h.MachineID,
		LocationTier: h.LocationTier,
		Version:      h.Version,
		SentAt:       time.Now().UTC().Format(time.RFC3339),
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(
		ctx, http.MethodPost,
		h.OrchestratorURL+"/api/fleet/heartbeat",
		bytes.NewReader(body),
	)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	startReq := time.Now()
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("heartbeat status %d", resp.StatusCode)
	}
	_ = startReq // future: write latency_self_ms back
	return nil
}

func sleep(ctx context.Context, d time.Duration) bool {
	if d <= 0 {
		return true
	}
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}
