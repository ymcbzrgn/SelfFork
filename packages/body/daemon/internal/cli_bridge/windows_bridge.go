// Windows PowerShell job-control bridge.
//
// This file provides the Windows fallback promised by the package doc: it maps
// the same Bridge contract onto PowerShell background-job control instead of
// tmux. A "session" is a named PowerShell background job:
//
//	ListSessions -> Get-Job                     (enumerate background jobs)
//	SendKeys     -> Start-Job -Name <target>    (run the keys as a named job)
//	CapturePane  -> Receive-Job -Name <target>  (read the job's accumulated output)
//
// The bridge shells out through the injectable Run field, so it is unit-testable
// without ever launching PowerShell.
package cli_bridge

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"strings"
)

// powershellExe is the Windows PowerShell host the bridge drives.
const powershellExe = "powershell"

// WindowsBridge drives PowerShell background jobs as CLI sessions.
type WindowsBridge struct {
	// Allow injecting a fake exec function in tests.
	Run func(ctx context.Context, name string, args ...string) ([]byte, error)
}

// Compile-time assertion that WindowsBridge satisfies the Bridge contract.
var _ Bridge = (*WindowsBridge)(nil)

// NewWindowsBridge returns a default real-PowerShell bridge.
func NewWindowsBridge() *WindowsBridge {
	return &WindowsBridge{
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

// psArgs wraps a PowerShell script in the standard non-interactive invocation.
func psArgs(script string) []string {
	return []string{"-NoProfile", "-NonInteractive", "-Command", script}
}

// psSingleQuote renders s as a single-quoted PowerShell literal, escaping any
// embedded single quotes by doubling them.
func psSingleQuote(s string) string {
	return "'" + strings.ReplaceAll(s, "'", "''") + "'"
}

// ListSessions enumerates PowerShell background jobs as sessions. A job whose
// State is "Running" is reported as attached, mirroring an attached tmux pane.
func (b *WindowsBridge) ListSessions(ctx context.Context) ([]Session, error) {
	const script = `Get-Job | ForEach-Object { "$($_.Name)|$($_.Id)|$($_.State)" }`
	out, err := b.Run(ctx, powershellExe, psArgs(script)...)
	if err != nil {
		return nil, err
	}
	var sessions []Session
	for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		parts := strings.SplitN(line, "|", 3)
		if len(parts) < 3 {
			continue
		}
		sessions = append(sessions, Session{
			Name:     strings.TrimSpace(parts[0]),
			ID:       strings.TrimSpace(parts[1]),
			Attached: strings.EqualFold(strings.TrimSpace(parts[2]), "Running"),
		})
	}
	return sessions, nil
}

// SendKeys runs keys as a named PowerShell background job (the session target),
// the job-control analogue of typing a command line into a tmux pane.
func (b *WindowsBridge) SendKeys(ctx context.Context, target, keys string) error {
	script := fmt.Sprintf("Start-Job -Name %s -ScriptBlock { %s } | Out-Null", psSingleQuote(target), keys)
	_, err := b.Run(ctx, powershellExe, psArgs(script)...)
	return err
}

// CapturePane returns the accumulated output of the named background job. The
// -Keep flag is non-destructive, so repeated captures behave like re-reading a
// tmux pane rather than draining the job.
func (b *WindowsBridge) CapturePane(ctx context.Context, target string) (string, error) {
	script := fmt.Sprintf("Receive-Job -Name %s -Keep", psSingleQuote(target))
	out, err := b.Run(ctx, powershellExe, psArgs(script)...)
	if err != nil {
		return "", err
	}
	return string(out), nil
}
