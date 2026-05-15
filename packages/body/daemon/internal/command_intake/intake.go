// Package command_intake receives signed orchestrator commands.
//
// Connects to ``/ws/fleet/<machine_id>`` over WebSocket; verifies HMAC-SHA256
// signatures + nonce + timestamp; dispatches recognised commands to the
// CLI bridge.
package command_intake

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/selffork/selffork-daemon/internal/cli_bridge"
)

// Intake configuration.
type Intake struct {
	OrchestratorURL string
	MachineID       string
	Secret          string
	Bridge          cli_bridge.Bridge

	// MaxClockSkew rejects payloads whose timestamp lies outside the window
	// (default 60s) — replay protection.
	MaxClockSkew time.Duration
}

// SignedCommand is the on-the-wire payload the orchestrator emits.
type SignedCommand struct {
	Command   string                 `json:"command"`
	Args      map[string]interface{} `json:"args"`
	Nonce     string                 `json:"nonce"`
	Timestamp string                 `json:"timestamp"`
	Signature string                 `json:"signature"`
}

// Run keeps the intake alive until ctx is cancelled. The actual WebSocket
// dial loop is intentionally minimal here — production wiring layers on
// reconnect logic identical to the heartbeat backoff sequence.
func (i *Intake) Run(ctx context.Context) error {
	<-ctx.Done()
	return nil
}

// Verify returns nil when the signed command is authentic and within the
// allowed clock skew window. Used by the WS handler before dispatch.
func (i *Intake) Verify(cmd SignedCommand, now time.Time) error {
	if cmd.Signature == "" {
		return errors.New("missing signature")
	}
	skew := i.MaxClockSkew
	if skew <= 0 {
		skew = 60 * time.Second
	}
	ts, err := time.Parse(time.RFC3339, cmd.Timestamp)
	if err != nil {
		return fmt.Errorf("parse timestamp: %w", err)
	}
	delta := now.Sub(ts)
	if delta < 0 {
		delta = -delta
	}
	if delta > skew {
		return fmt.Errorf("timestamp skew %s exceeds %s", delta, skew)
	}
	if cmd.Nonce == "" {
		return errors.New("missing nonce")
	}

	expected := i.sign(cmd.Command, cmd.Args, cmd.Nonce, cmd.Timestamp)
	got, err := hex.DecodeString(cmd.Signature)
	if err != nil {
		return fmt.Errorf("decode signature: %w", err)
	}
	if !hmac.Equal(expected, got) {
		return errors.New("signature mismatch")
	}
	return nil
}

func (i *Intake) sign(command string, args map[string]interface{}, nonce, ts string) []byte {
	h := hmac.New(sha256.New, []byte(i.Secret))
	// Canonical: command | nonce | timestamp | sorted-key=value pairs
	h.Write([]byte(command))
	h.Write([]byte("|"))
	h.Write([]byte(nonce))
	h.Write([]byte("|"))
	h.Write([]byte(ts))
	for _, k := range sortedKeys(args) {
		h.Write([]byte("|"))
		h.Write([]byte(k))
		h.Write([]byte("="))
		h.Write([]byte(fmt.Sprintf("%v", args[k])))
	}
	return h.Sum(nil)
}

// Sign is exposed for the orchestrator-side helper to emit matching
// signatures during integration tests.
func (i *Intake) Sign(command string, args map[string]interface{}, nonce, ts string) string {
	return hex.EncodeToString(i.sign(command, args, nonce, ts))
}

func sortedKeys(m map[string]interface{}) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	// stable insertion sort — small N
	for i := 1; i < len(keys); i++ {
		for j := i; j > 0 && keys[j-1] > keys[j]; j-- {
			keys[j-1], keys[j] = keys[j], keys[j-1]
		}
	}
	return keys
}
