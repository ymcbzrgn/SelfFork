// Package registration performs one-time daemon self-registration with the
// home orchestrator's fleet registry.
//
// A fresh daemon must POST {machine_id, hostname, location_tier, version} to
// /api/fleet/register before any heartbeat or state report will be accepted:
// the server keys heartbeat/state ingest on the machine_id already existing in
// its FleetRegistry and returns HTTP 404 otherwise. Registration issues an
// auth_key for future authenticated ingest; the current heartbeat/state
// endpoints do not require it.
package registration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/selffork/selffork-daemon/internal/heartbeat"
)

// Config carries the fields required to register a daemon. It mirrors the
// http-client + identity conventions used by the heartbeat package.
type Config struct {
	OrchestratorURL string
	MachineID       string
	Hostname        string
	LocationTier    string
	Version         string

	// Client allows injecting a fake HTTP client in tests. When nil a
	// default client with a 10s timeout is used.
	Client *http.Client
}

// RegisterResult is the outcome of a successful registration attempt.
type RegisterResult struct {
	// AuthKey is the server-issued key returned on a fresh (HTTP 201)
	// registration. It is empty when the machine was already registered
	// (see AlreadyRegistered).
	AuthKey string
	// AlreadyRegistered is true when the server reported the machine_id as
	// already present (HTTP 409). This is treated as success: the record
	// exists server-side, so heartbeat/state ingest will be accepted.
	AlreadyRegistered bool
}

// StatusError is returned when the server responds with an unexpected non-2xx
// (and non-409) status code.
type StatusError struct {
	StatusCode int
	Body       string
}

func (e *StatusError) Error() string {
	if e.Body != "" {
		return fmt.Sprintf("register: unexpected status %d: %s", e.StatusCode, e.Body)
	}
	return fmt.Sprintf("register: unexpected status %d", e.StatusCode)
}

type registerRequest struct {
	MachineID    string `json:"machine_id"`
	Hostname     string `json:"hostname"`
	LocationTier string `json:"location_tier"`
	Version      string `json:"version"`
}

type registerResponse struct {
	AuthKey string `json:"auth_key"`
}

// Register performs a single self-registration attempt against
// /api/fleet/register. On HTTP 201 it parses and returns the issued
// auth_key. HTTP 409 (already registered) is reported as a successful,
// idempotent result so daemon restarts do not fail. Any other non-2xx status
// yields a *StatusError; transport failures are wrapped and returned.
func Register(ctx context.Context, cfg Config) (RegisterResult, error) {
	client := cfg.Client
	if client == nil {
		client = &http.Client{Timeout: 10 * time.Second}
	}
	locationTier := cfg.LocationTier
	if locationTier == "" {
		locationTier = "auto"
	}
	hostname := cfg.Hostname
	if hostname == "" {
		hostname = cfg.MachineID
	}

	body, err := json.Marshal(registerRequest{
		MachineID:    cfg.MachineID,
		Hostname:     hostname,
		LocationTier: locationTier,
		Version:      cfg.Version,
	})
	if err != nil {
		return RegisterResult{}, fmt.Errorf("register: marshal payload: %w", err)
	}

	req, err := http.NewRequestWithContext(
		ctx, http.MethodPost,
		cfg.OrchestratorURL+"/api/fleet/register",
		bytes.NewReader(body),
	)
	if err != nil {
		return RegisterResult{}, fmt.Errorf("register: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return RegisterResult{}, fmt.Errorf("register: post: %w", err)
	}
	defer resp.Body.Close()

	switch {
	case resp.StatusCode == http.StatusConflict:
		// 409: already registered. The record exists server-side, so
		// heartbeat/state ingest will be accepted. Treat as success.
		return RegisterResult{AlreadyRegistered: true}, nil
	case resp.StatusCode >= 200 && resp.StatusCode < 300:
		var parsed registerResponse
		if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
			return RegisterResult{}, fmt.Errorf("register: decode response: %w", err)
		}
		return RegisterResult{AuthKey: parsed.AuthKey}, nil
	default:
		snippet, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return RegisterResult{}, &StatusError{
			StatusCode: resp.StatusCode,
			Body:       strings.TrimSpace(string(snippet)),
		}
	}
}

// RegisterWithRetry calls Register, retrying on transport or unexpected-status
// failures using the shared heartbeat backoff schedule until it succeeds or
// ctx is cancelled. This mirrors the daemon's heartbeat resilience: a
// transiently-unreachable orchestrator must not crash the daemon, and no
// heartbeat/state goroutine should start until the machine is registered (so
// the fleet ingest never 404s). logf, when non-nil, receives one line per
// failed attempt. On ctx cancellation it returns ctx.Err().
func RegisterWithRetry(
	ctx context.Context,
	cfg Config,
	logf func(format string, args ...any),
) (RegisterResult, error) {
	var backoff time.Duration
	for {
		res, err := Register(ctx, cfg)
		if err == nil {
			return res, nil
		}
		if ctx.Err() != nil {
			return RegisterResult{}, ctx.Err()
		}
		if logf != nil {
			logf("registration attempt failed: %v", err)
		}
		backoff = heartbeat.NextBackoff(backoff)
		if !sleep(ctx, backoff) {
			return RegisterResult{}, ctx.Err()
		}
	}
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
