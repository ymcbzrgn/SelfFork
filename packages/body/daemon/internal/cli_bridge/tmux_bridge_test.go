package cli_bridge

import (
	"context"
	"errors"
	"strings"
	"testing"
)

func TestListSessionsParsesOutput(t *testing.T) {
	bridge := &TmuxBridge{
		Run: func(ctx context.Context, name string, args ...string) ([]byte, error) {
			if name != "tmux" {
				t.Fatalf("unexpected exec name: %s", name)
			}
			return []byte("dev|$0|1\nmail|$1|0\n"), nil
		},
	}
	sessions, err := bridge.ListSessions(context.Background())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(sessions) != 2 {
		t.Fatalf("expected 2 sessions, got %d", len(sessions))
	}
	if sessions[0].Name != "dev" || !sessions[0].Attached {
		t.Errorf("first session mismatch: %+v", sessions[0])
	}
	if sessions[1].Name != "mail" || sessions[1].Attached {
		t.Errorf("second session mismatch: %+v", sessions[1])
	}
}

func TestListSessionsHandlesNoServer(t *testing.T) {
	bridge := &TmuxBridge{
		Run: func(_ context.Context, _ string, _ ...string) ([]byte, error) {
			return nil, errors.New("error connecting to /tmp/tmux-501/default (no server running on /tmp/tmux-501/default)")
		},
	}
	sessions, err := bridge.ListSessions(context.Background())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if sessions != nil {
		t.Errorf("expected nil sessions, got %+v", sessions)
	}
}

func TestSendKeysCommand(t *testing.T) {
	var captured []string
	bridge := &TmuxBridge{
		Run: func(_ context.Context, name string, args ...string) ([]byte, error) {
			captured = append([]string{name}, args...)
			return nil, nil
		},
	}
	if err := bridge.SendKeys(context.Background(), "dev:0", "ls\n"); err != nil {
		t.Fatalf("err: %v", err)
	}
	if got := strings.Join(captured, " "); got != "tmux send-keys -t dev:0 ls\n C-m" {
		t.Errorf("captured wrong command: %q", got)
	}
}

func TestCapturePaneReturnsString(t *testing.T) {
	bridge := &TmuxBridge{
		Run: func(_ context.Context, _ string, _ ...string) ([]byte, error) {
			return []byte("hello\nworld\n"), nil
		},
	}
	out, err := bridge.CapturePane(context.Background(), "dev:0")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if out != "hello\nworld\n" {
		t.Errorf("captured wrong output: %q", out)
	}
}
