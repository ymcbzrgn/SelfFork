//go:build !windows

package main

import "os"

// listVolumes on non-Windows hosts treats the filesystem root as the only
// "volume". (The shipped product targets Windows; this keeps the tool
// buildable and runnable on macOS/Linux for development.)
func listVolumes(includeRemovable bool) []string {
	return []string{"/"}
}

func isReparsePoint(info os.FileInfo) bool {
	if info == nil {
		return false
	}
	return info.Mode()&os.ModeSymlink != 0
}

func userProfilesRoot() string {
	if h, err := os.UserHomeDir(); err == nil {
		// e.g. /home/<user> -> /home ; /Users/<user> -> /Users
		for i := len(h) - 1; i > 0; i-- {
			if h[i] == '/' {
				return h[:i]
			}
		}
	}
	return "/home"
}

func machineClaudeDirs() []string {
	return []string{"/etc/claude-code", "/Library/Application Support/ClaudeCode"}
}

// On non-Windows we don't auto-elevate; treat as "already privileged enough"
// so the all-users walk just proceeds and logs any permission errors.
func isElevated() bool        { return true }
func relaunchElevated() error { return nil }
