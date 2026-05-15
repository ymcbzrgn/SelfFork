// Package cli_bridge wraps platform-specific CLI control surfaces.
//
// On macOS / Linux it shells out to ``tmux send-keys`` / ``tmux capture-pane``.
// Windows fallback is PowerShell job control (lands in M5 follow-up).
package cli_bridge

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"strings"
)

// Bridge is the contract a CLI bridge must satisfy.
type Bridge interface {
	ListSessions(ctx context.Context) ([]Session, error)
	SendKeys(ctx context.Context, target, keys string) error
	CapturePane(ctx context.Context, target string) (string, error)
}

// Session describes a tmux session.
type Session struct {
	Name     string `json:"name"`
	ID       string `json:"id"`
	Attached bool   `json:"attached"`
}

// TmuxBridge shells out to tmux.
type TmuxBridge struct {
	// Allow injecting a fake exec function in tests.
	Run func(ctx context.Context, name string, args ...string) ([]byte, error)
}

// NewTmuxBridge returns a default real-tmux bridge.
func NewTmuxBridge() *TmuxBridge {
	return &TmuxBridge{
		Run: func(ctx context.Context, name string, args ...string) ([]byte, error) {
			cmd := exec.CommandContext(ctx, name, args...)
			var stdout, stderr bytes.Buffer
			cmd.Stdout = &stdout
			cmd.Stderr = &stderr
			if err := cmd.Run(); err != nil {
				return nil, fmt.Errorf("%s %v: %w (stderr=%q)", name, args, err, stderr.String())
			}
			return stdout.Bytes(), nil
		},
	}
}

// ListSessions enumerates tmux sessions.
func (b *TmuxBridge) ListSessions(ctx context.Context) ([]Session, error) {
	out, err := b.Run(ctx, "tmux", "list-sessions",
		"-F", "#{session_name}|#{session_id}|#{session_attached}")
	if err != nil {
		// tmux returns non-zero when no server is running. Treat as empty.
		if strings.Contains(err.Error(), "no server running") {
			return nil, nil
		}
		return nil, err
	}
	var sessions []Session
	for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		if line == "" {
			continue
		}
		parts := strings.SplitN(line, "|", 3)
		if len(parts) < 3 {
			continue
		}
		sessions = append(sessions, Session{
			Name:     parts[0],
			ID:       parts[1],
			Attached: parts[2] == "1",
		})
	}
	return sessions, nil
}

// SendKeys sends ``keys`` followed by Enter to the given tmux target.
func (b *TmuxBridge) SendKeys(ctx context.Context, target, keys string) error {
	_, err := b.Run(ctx, "tmux", "send-keys", "-t", target, keys, "C-m")
	return err
}

// CapturePane returns the visible content of the given tmux target.
func (b *TmuxBridge) CapturePane(ctx context.Context, target string) (string, error) {
	out, err := b.Run(ctx, "tmux", "capture-pane", "-p", "-t", target)
	if err != nil {
		return "", err
	}
	return string(out), nil
}
