// Package command_intake receives signed orchestrator commands.
//
// Connects to /ws/fleet/<machine_id> over WebSocket; verifies HMAC-SHA256
// signatures + nonce + timestamp; dispatches recognised commands to the
// CLI bridge.
package command_intake

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/url"
	"strings"
	"time"

	"github.com/gorilla/websocket"

	"github.com/selffork/selffork-daemon/internal/cli_bridge"
	"github.com/selffork/selffork-daemon/internal/heartbeat"
)

// Intake configuration.
type Intake struct {
	OrchestratorURL string
	MachineID       string
	Secret          string
	Bridge          cli_bridge.Bridge

	// MaxClockSkew rejects payloads whose timestamp lies outside the window
	// (default 60s) - replay protection.
	MaxClockSkew time.Duration

	// HandshakeTimeout bounds each WebSocket dial (default 10s).
	HandshakeTimeout time.Duration

	// backoff computes the next reconnect delay from the previous one. It
	// defaults to heartbeat.NextBackoff (1s -> 2s -> 5s -> 15s -> 30s -> 60s);
	// tests inject a fast schedule.
	backoff func(time.Duration) time.Duration

	// logf is the log sink (defaults to log.Printf); tests may capture it.
	logf func(format string, args ...interface{})
}

// SignedCommand is the on-the-wire payload the orchestrator emits.
type SignedCommand struct {
	Command   string                 `json:"command"`
	Args      map[string]interface{} `json:"args"`
	Nonce     string                 `json:"nonce"`
	Timestamp string                 `json:"timestamp"`
	Signature string                 `json:"signature"`
}

// Run dials the orchestrator's /ws/fleet/<machine_id> endpoint and serves
// signed commands until ctx is cancelled. Transport failures are non-fatal:
// the loop reconnects with the heartbeat backoff schedule and never panics.
// Run returns nil once ctx is cancelled.
func (i *Intake) Run(ctx context.Context) error {
	nextBackoff := i.backoff
	if nextBackoff == nil {
		nextBackoff = heartbeat.NextBackoff
	}
	logf := i.logf
	if logf == nil {
		logf = log.Printf
	}

	var delay time.Duration
	for {
		if ctx.Err() != nil {
			return nil
		}

		err := i.connectAndServe(ctx)
		if ctx.Err() != nil {
			// Shutdown requested; any error here is just the closing socket.
			return nil
		}
		if err != nil {
			delay = nextBackoff(delay)
			logf("command intake: connection to %s lost: %v; reconnecting in %s", i.wsURL(), err, delay)
		} else {
			// Server closed the stream cleanly; reconnect promptly.
			delay = nextBackoff(delay)
			logf("command intake: connection to %s closed; reconnecting in %s", i.wsURL(), delay)
		}
		if !sleep(ctx, delay) {
			return nil
		}
	}
}

// connectAndServe dials once and reads frames until the socket errors, the
// server closes it, or ctx is cancelled. It returns the read error (nil on a
// clean close) so Run can decide whether/how long to back off.
func (i *Intake) connectAndServe(ctx context.Context) error {
	handshake := i.HandshakeTimeout
	if handshake <= 0 {
		handshake = 10 * time.Second
	}
	dialer := &websocket.Dialer{HandshakeTimeout: handshake}

	conn, resp, err := dialer.DialContext(ctx, i.wsURL(), nil)
	if err != nil {
		if resp != nil {
			return fmt.Errorf("dial: %w (status %d)", err, resp.StatusCode)
		}
		return fmt.Errorf("dial: %w", err)
	}
	defer conn.Close()

	// Close the socket when ctx is cancelled to unblock the blocking read.
	done := make(chan struct{})
	defer close(done)
	go func() {
		select {
		case <-ctx.Done():
			_ = conn.Close()
		case <-done:
		}
	}()

	for {
		msgType, data, err := conn.ReadMessage()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			if websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
				return nil
			}
			return err
		}
		if msgType != websocket.TextMessage && msgType != websocket.BinaryMessage {
			continue
		}
		i.handleFrame(ctx, data)
	}
}

// handleFrame decodes, verifies, and dispatches a single wire frame. All
// failures are logged and swallowed so one bad frame never drops the stream.
func (i *Intake) handleFrame(ctx context.Context, data []byte) {
	logf := i.logf
	if logf == nil {
		logf = log.Printf
	}
	var cmd SignedCommand
	if err := json.Unmarshal(data, &cmd); err != nil {
		logf("command intake: dropping malformed frame: %v", err)
		return
	}
	if err := i.Verify(cmd, time.Now().UTC()); err != nil {
		logf("command intake: rejecting command %q: %v", cmd.Command, err)
		return
	}
	if err := i.dispatch(ctx, cmd); err != nil {
		logf("command intake: dispatch of %q failed: %v", cmd.Command, err)
	}
}

// dispatch routes a verified command to the CLI bridge. It never reimplements
// the bridge - it calls the interface main.go already wired in.
func (i *Intake) dispatch(ctx context.Context, cmd SignedCommand) error {
	if i.Bridge == nil {
		return errors.New("no CLI bridge configured")
	}
	switch cmd.Command {
	case "send_keys":
		target, ok := stringArg(cmd.Args, "target")
		if !ok {
			return errors.New("send_keys: missing target")
		}
		keys, _ := stringArg(cmd.Args, "keys")
		return i.Bridge.SendKeys(ctx, target, keys)
	case "capture_pane":
		target, ok := stringArg(cmd.Args, "target")
		if !ok {
			return errors.New("capture_pane: missing target")
		}
		_, err := i.Bridge.CapturePane(ctx, target)
		return err
	case "list_sessions":
		_, err := i.Bridge.ListSessions(ctx)
		return err
	default:
		return fmt.Errorf("unknown command %q", cmd.Command)
	}
}

// wsURL builds the ws(s) URL for this machine's fleet channel, normalising an
// http(s) orchestrator URL to the ws(s) scheme.
func (i *Intake) wsURL() string {
	base := strings.TrimRight(i.OrchestratorURL, "/")
	switch {
	case strings.HasPrefix(base, "https://"):
		base = "wss://" + strings.TrimPrefix(base, "https://")
	case strings.HasPrefix(base, "http://"):
		base = "ws://" + strings.TrimPrefix(base, "http://")
	}
	return base + "/ws/fleet/" + url.PathEscape(i.MachineID)
}

func stringArg(args map[string]interface{}, key string) (string, bool) {
	if args == nil {
		return "", false
	}
	v, ok := args[key].(string)
	return v, ok && v != ""
}

// sleep waits for d or ctx cancellation. It returns false when ctx is
// cancelled first, signalling the caller to stop.
func sleep(ctx context.Context, d time.Duration) bool {
	if d <= 0 {
		return ctx.Err() == nil
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
	// stable insertion sort - small N
	for i := 1; i < len(keys); i++ {
		for j := i; j > 0 && keys[j-1] > keys[j]; j-- {
			keys[j-1], keys[j] = keys[j], keys[j-1]
		}
	}
	return keys
}
