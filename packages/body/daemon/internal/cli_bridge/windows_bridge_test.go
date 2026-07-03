package cli_bridge

import (
	"context"
	"errors"
	"strings"
	"testing"
)

func TestWindowsListSessionsParsesOutput(t *testing.T) {
	var captured []string
	bridge := &WindowsBridge{
		Run: func(ctx context.Context, name string, args ...string) ([]byte, error) {
			captured = append([]string{name}, args...)
			if name != "powershell" {
				t.Fatalf("unexpected exec name: %s", name)
			}
			// PowerShell emits CRLF line endings.
			return []byte("dev|3|Running\r\nmail|4|Completed\r\n"), nil
		},
	}
	sessions, err := bridge.ListSessions(context.Background())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(sessions) != 2 {
		t.Fatalf("expected 2 sessions, got %d", len(sessions))
	}
	if sessions[0].Name != "dev" || sessions[0].ID != "3" || !sessions[0].Attached {
		t.Errorf("first session mismatch: %+v", sessions[0])
	}
	if sessions[1].Name != "mail" || sessions[1].ID != "4" || sessions[1].Attached {
		t.Errorf("second session mismatch: %+v", sessions[1])
	}
	got := strings.Join(captured, " ")
	if !strings.Contains(got, "Get-Job") {
		t.Errorf("expected Get-Job in command, got %q", got)
	}
	if !strings.Contains(got, "-NoProfile") || !strings.Contains(got, "-NonInteractive") {
		t.Errorf("expected non-interactive flags, got %q", got)
	}
}

func TestWindowsListSessionsEmpty(t *testing.T) {
	bridge := &WindowsBridge{
		Run: func(_ context.Context, _ string, _ ...string) ([]byte, error) {
			return []byte("\r\n"), nil
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

func TestWindowsListSessionsError(t *testing.T) {
	bridge := &WindowsBridge{
		Run: func(_ context.Context, _ string, _ ...string) ([]byte, error) {
			return nil, errors.New("powershell: executable file not found in %PATH%")
		},
	}
	if _, err := bridge.ListSessions(context.Background()); err == nil {
		t.Fatal("expected error, got nil")
	}
}

func TestWindowsSendKeysCommand(t *testing.T) {
	var captured []string
	bridge := &WindowsBridge{
		Run: func(_ context.Context, name string, args ...string) ([]byte, error) {
			captured = append([]string{name}, args...)
			return nil, nil
		},
	}
	if err := bridge.SendKeys(context.Background(), "dev", "Get-ChildItem"); err != nil {
		t.Fatalf("err: %v", err)
	}
	if captured[0] != "powershell" {
		t.Fatalf("expected powershell host, got %q", captured[0])
	}
	script := captured[len(captured)-1]
	if !strings.Contains(script, "Start-Job -Name 'dev'") {
		t.Errorf("expected Start-Job for target, got %q", script)
	}
	if !strings.Contains(script, "Get-ChildItem") {
		t.Errorf("expected keys inside scriptblock, got %q", script)
	}
}

func TestWindowsSendKeysEscapesTarget(t *testing.T) {
	var script string
	bridge := &WindowsBridge{
		Run: func(_ context.Context, _ string, args ...string) ([]byte, error) {
			script = args[len(args)-1]
			return nil, nil
		},
	}
	if err := bridge.SendKeys(context.Background(), "de'v", "echo hi"); err != nil {
		t.Fatalf("err: %v", err)
	}
	if !strings.Contains(script, "Start-Job -Name 'de''v'") {
		t.Errorf("expected doubled single quote in target, got %q", script)
	}
}

func TestWindowsSendKeysError(t *testing.T) {
	bridge := &WindowsBridge{
		Run: func(_ context.Context, _ string, _ ...string) ([]byte, error) {
			return nil, errors.New("boom")
		},
	}
	if err := bridge.SendKeys(context.Background(), "dev", "echo hi"); err == nil {
		t.Fatal("expected error, got nil")
	}
}

func TestWindowsCapturePaneReturnsString(t *testing.T) {
	var captured []string
	bridge := &WindowsBridge{
		Run: func(_ context.Context, name string, args ...string) ([]byte, error) {
			captured = append([]string{name}, args...)
			return []byte("hello\r\nworld\r\n"), nil
		},
	}
	out, err := bridge.CapturePane(context.Background(), "dev")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if out != "hello\r\nworld\r\n" {
		t.Errorf("captured wrong output: %q", out)
	}
	script := captured[len(captured)-1]
	if !strings.Contains(script, "Receive-Job -Name 'dev' -Keep") {
		t.Errorf("expected Receive-Job for target, got %q", script)
	}
}

func TestWindowsCapturePaneError(t *testing.T) {
	bridge := &WindowsBridge{
		Run: func(_ context.Context, _ string, _ ...string) ([]byte, error) {
			return nil, errors.New("no job named dev")
		},
	}
	if _, err := bridge.CapturePane(context.Background(), "dev"); err == nil {
		t.Fatal("expected error, got nil")
	}
}
