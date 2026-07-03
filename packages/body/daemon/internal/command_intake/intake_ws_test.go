package command_intake

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"

	"github.com/selffork/selffork-daemon/internal/cli_bridge"
)

// fastBackoff collapses the reconnect schedule so transport tests stay quick.
func fastBackoff(time.Duration) time.Duration { return 5 * time.Millisecond }

// sendKeysCall records a single Bridge.SendKeys invocation.
type sendKeysCall struct {
	target string
	keys   string
}

// fakeBridge is a cli_bridge.Bridge that records SendKeys dispatches on a
// buffered channel. Sends are non-blocking so the intake read loop is never
// wedged by a test that has stopped reading.
type fakeBridge struct {
	calls chan sendKeysCall
}

func newFakeBridge() *fakeBridge {
	return &fakeBridge{calls: make(chan sendKeysCall, 8)}
}

func (f *fakeBridge) ListSessions(context.Context) ([]cli_bridge.Session, error) {
	return nil, nil
}

func (f *fakeBridge) SendKeys(_ context.Context, target, keys string) error {
	select {
	case f.calls <- sendKeysCall{target: target, keys: keys}:
	default:
	}
	return nil
}

func (f *fakeBridge) CapturePane(context.Context, string) (string, error) {
	return "", nil
}

// signedFrame builds a wire-ready, authentically-signed SignedCommand frame.
func signedFrame(secret, command string, args map[string]interface{}) []byte {
	signer := &Intake{Secret: secret}
	ts := time.Now().UTC().Format(time.RFC3339)
	nonce := "nonce-" + command
	cmd := SignedCommand{
		Command:   command,
		Args:      args,
		Nonce:     nonce,
		Timestamp: ts,
		Signature: signer.Sign(command, args, nonce, ts),
	}
	raw, _ := json.Marshal(cmd)
	return raw
}

var testUpgrader = websocket.Upgrader{}

// wsServer stands up an httptest server that upgrades to WebSocket and hands
// the connection to handler. handler returning closes the socket.
func wsServer(t *testing.T, handler func(*websocket.Conn)) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := testUpgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()
		handler(conn)
	}))
}

func newTestIntake(url, secret string, bridge cli_bridge.Bridge) *Intake {
	return &Intake{
		OrchestratorURL: url,
		MachineID:       "work-ubuntu",
		Secret:          secret,
		Bridge:          bridge,
		backoff:         fastBackoff,
		logf:            func(string, ...interface{}) {},
	}
}

func TestRunDispatchesVerifiedCommand(t *testing.T) {
	const secret = "topsecret"
	frame := signedFrame(secret, "send_keys", map[string]interface{}{"target": "dev:0", "keys": "ls"})

	srv := wsServer(t, func(conn *websocket.Conn) {
		_ = conn.WriteMessage(websocket.TextMessage, frame)
		time.Sleep(200 * time.Millisecond)
	})
	defer srv.Close()

	bridge := newFakeBridge()
	intake := newTestIntake(srv.URL, secret, bridge)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() { _ = intake.Run(ctx) }()

	select {
	case call := <-bridge.calls:
		if call.target != "dev:0" || call.keys != "ls" {
			t.Fatalf("dispatched wrong args: %+v", call)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("verified command was never dispatched")
	}
}

func TestRunRejectsBadSignature(t *testing.T) {
	const secret = "topsecret"
	// Signed with the wrong secret: Verify must reject it and it must never
	// reach the bridge. A trailing good frame proves the stream survives.
	bad := signedFrame("WRONG-SECRET", "send_keys", map[string]interface{}{"target": "attacker", "keys": "rm -rf"})
	good := signedFrame(secret, "send_keys", map[string]interface{}{"target": "legit", "keys": "ls"})

	srv := wsServer(t, func(conn *websocket.Conn) {
		_ = conn.WriteMessage(websocket.TextMessage, bad)
		_ = conn.WriteMessage(websocket.TextMessage, good)
		time.Sleep(200 * time.Millisecond)
	})
	defer srv.Close()

	bridge := newFakeBridge()
	intake := newTestIntake(srv.URL, secret, bridge)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() { _ = intake.Run(ctx) }()

	select {
	case call := <-bridge.calls:
		if call.target != "legit" {
			t.Fatalf("bad-signature frame was dispatched: %+v", call)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("good command was never dispatched")
	}

	// No second dispatch: the tampered frame must have been dropped.
	select {
	case extra := <-bridge.calls:
		t.Fatalf("unexpected extra dispatch: %+v", extra)
	case <-time.After(150 * time.Millisecond):
	}
}

func TestRunReconnectsAfterTransportDrop(t *testing.T) {
	const secret = "topsecret"
	good := signedFrame(secret, "send_keys", map[string]interface{}{"target": "after-reconnect", "keys": "y"})

	var conns int32
	srv := wsServer(t, func(conn *websocket.Conn) {
		if atomic.AddInt32(&conns, 1) == 1 {
			// First connection drops immediately (abnormal closure).
			return
		}
		_ = conn.WriteMessage(websocket.TextMessage, good)
		time.Sleep(200 * time.Millisecond)
	})
	defer srv.Close()

	bridge := newFakeBridge()
	intake := newTestIntake(srv.URL, secret, bridge)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() { _ = intake.Run(ctx) }()

	select {
	case call := <-bridge.calls:
		if call.target != "after-reconnect" {
			t.Fatalf("dispatched wrong args after reconnect: %+v", call)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("no dispatch after reconnect")
	}
	if got := atomic.LoadInt32(&conns); got < 2 {
		t.Fatalf("expected at least 2 connections (reconnect), got %d", got)
	}
}

func TestRunReturnsCleanlyOnContextCancel(t *testing.T) {
	srv := wsServer(t, func(conn *websocket.Conn) {
		time.Sleep(time.Second) // hold the connection open
	})
	defer srv.Close()

	intake := newTestIntake(srv.URL, "topsecret", newFakeBridge())

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- intake.Run(ctx) }()

	time.Sleep(80 * time.Millisecond) // let the dial land
	cancel()

	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("Run returned %v, want nil on ctx cancel", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("Run did not return promptly after ctx cancel")
	}
}

func TestWSURLNormalisesScheme(t *testing.T) {
	cases := []struct {
		base    string
		machine string
		want    string
	}{
		{"http://host:8000", "m", "ws://host:8000/ws/fleet/m"},
		{"https://host", "m", "wss://host/ws/fleet/m"},
		{"ws://host/", "m", "ws://host/ws/fleet/m"},
		{"http://host", "work box", "ws://host/ws/fleet/work%20box"},
	}
	for _, c := range cases {
		i := &Intake{OrchestratorURL: c.base, MachineID: c.machine}
		if got := i.wsURL(); got != c.want {
			t.Errorf("wsURL(%q,%q) = %q, want %q", c.base, c.machine, got, c.want)
		}
	}
}
