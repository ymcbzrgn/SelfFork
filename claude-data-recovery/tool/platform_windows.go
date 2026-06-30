//go:build windows

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

const fileAttributeReparsePoint = 0x400

// listVolumes returns the root paths ("C:\\", "D:\\", ...) of fixed drives,
// plus removable drives when includeRemovable is set. Network and CD-ROM
// drives are always skipped.
func listVolumes(includeRemovable bool) []string {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	getLogicalDrives := kernel32.NewProc("GetLogicalDrives")
	getDriveType := kernel32.NewProc("GetDriveTypeW")

	r1, _, _ := getLogicalDrives.Call()
	mask := uint32(r1)

	var roots []string
	for i := 0; i < 26; i++ {
		if mask&(1<<uint(i)) == 0 {
			continue
		}
		root := string(rune('A'+i)) + `:\`
		p, err := syscall.UTF16PtrFromString(root)
		if err != nil {
			continue
		}
		dt, _, _ := getDriveType.Call(uintptr(unsafe.Pointer(p)))
		// DRIVE_REMOVABLE=2, DRIVE_FIXED=3, DRIVE_REMOTE=4, DRIVE_CDROM=5, DRIVE_RAMDISK=6
		switch dt {
		case 3, 6:
			roots = append(roots, root)
		case 2:
			if includeRemovable {
				roots = append(roots, root)
			}
		}
	}
	return roots
}

// isReparsePoint reports whether info is a junction/symlink/mount point, which
// we must not follow during a walk (avoids infinite loops like
// C:\Users\All Users -> C:\ProgramData).
func isReparsePoint(info os.FileInfo) bool {
	if info == nil {
		return false
	}
	if d, ok := info.Sys().(*syscall.Win32FileAttributeData); ok {
		return d.FileAttributes&fileAttributeReparsePoint != 0
	}
	return info.Mode()&os.ModeSymlink != 0
}

func userProfilesRoot() string {
	if up := os.Getenv("USERPROFILE"); up != "" {
		return filepath.Dir(up)
	}
	return `C:\Users`
}

// machineClaudeDirs returns machine-wide (non-per-user) Claude locations:
// enterprise managed-settings and any program-level config.
func machineClaudeDirs() []string {
	var out []string
	for _, env := range []string{"ProgramData", "ProgramFiles", "ProgramFiles(x86)"} {
		if base := os.Getenv(env); base != "" {
			out = append(out, filepath.Join(base, "ClaudeCode"))
		}
	}
	return out
}

// isElevated reports whether the process is running with an elevated
// (Administrator) token.
func isElevated() bool {
	proc, err := syscall.GetCurrentProcess()
	if err != nil {
		return false
	}
	var token syscall.Token
	if err := syscall.OpenProcessToken(proc, syscall.TOKEN_QUERY, &token); err != nil {
		return false
	}
	defer token.Close()

	advapi32 := syscall.NewLazyDLL("advapi32.dll")
	getTokenInformation := advapi32.NewProc("GetTokenInformation")
	const tokenElevation = 20 // TokenElevation
	var elevation uint32
	var retLen uint32
	r1, _, _ := getTokenInformation.Call(
		uintptr(token),
		uintptr(tokenElevation),
		uintptr(unsafe.Pointer(&elevation)),
		unsafe.Sizeof(elevation),
		uintptr(unsafe.Pointer(&retLen)),
	)
	return r1 != 0 && elevation != 0
}

// relaunchElevated re-runs this exe with the same args under a UAC elevation
// prompt. Returns nil if the elevated process was launched (caller should exit).
func relaunchElevated() error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	verb, _ := syscall.UTF16PtrFromString("runas")
	exep, _ := syscall.UTF16PtrFromString(exe)
	argp, _ := syscall.UTF16PtrFromString(quoteArgs(os.Args[1:]))
	cwd, _ := os.Getwd()
	cwdp, _ := syscall.UTF16PtrFromString(cwd)

	shell32 := syscall.NewLazyDLL("shell32.dll")
	shellExecute := shell32.NewProc("ShellExecuteW")
	const swShowNormal = 1
	r1, _, _ := shellExecute.Call(
		0,
		uintptr(unsafe.Pointer(verb)),
		uintptr(unsafe.Pointer(exep)),
		uintptr(unsafe.Pointer(argp)),
		uintptr(unsafe.Pointer(cwdp)),
		uintptr(swShowNormal),
	)
	if r1 <= 32 { // ShellExecute returns >32 on success
		return fmt.Errorf("ShellExecuteW failed (code %d)", r1)
	}
	return nil
}

func quoteArgs(args []string) string {
	parts := make([]string, 0, len(args))
	for _, a := range args {
		if strings.ContainsAny(a, " \t\"") {
			a = `"` + strings.ReplaceAll(a, `"`, `\"`) + `"`
		}
		parts = append(parts, a)
	}
	return strings.Join(parts, " ")
}
