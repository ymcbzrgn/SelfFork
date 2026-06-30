//go:build windows

package main

import (
	"errors"
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

// driveKind classifies the volume a path lives on: removable | fixed | remote |
// cdrom | ramdisk | unknown. Used to warn when output lands on an internal disk.
func driveKind(path string) string {
	vol := filepath.VolumeName(path)
	if vol == "" {
		return "unknown"
	}
	p, err := syscall.UTF16PtrFromString(vol + `\`)
	if err != nil {
		return "unknown"
	}
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	getDriveType := kernel32.NewProc("GetDriveTypeW")
	dt, _, _ := getDriveType.Call(uintptr(unsafe.Pointer(p)))
	switch dt {
	case 2:
		return "removable"
	case 3:
		return "fixed"
	case 4:
		return "remote"
	case 5:
		return "cdrom"
	case 6:
		return "ramdisk"
	default:
		return "unknown"
	}
}

// freeBytes returns the bytes available to the caller on the volume holding dir.
// dir must exist. ok=false if the query failed.
func freeBytes(dir string) (free uint64, ok bool) {
	p, err := syscall.UTF16PtrFromString(dir)
	if err != nil {
		return 0, false
	}
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	proc := kernel32.NewProc("GetDiskFreeSpaceExW")
	var freeToCaller, total, totalFree uint64
	r1, _, _ := proc.Call(
		uintptr(unsafe.Pointer(p)),
		uintptr(unsafe.Pointer(&freeToCaller)),
		uintptr(unsafe.Pointer(&total)),
		uintptr(unsafe.Pointer(&totalFree)),
	)
	if r1 == 0 {
		return 0, false
	}
	return freeToCaller, true
}

// classifyErr maps a Win32 error to a copy-loop action: abort-* (whole-run
// stopper), retry (transient lock), or skip (log and move on).
func classifyErr(err error) string {
	var e syscall.Errno
	if !errors.As(err, &e) {
		return "skip"
	}
	switch uintptr(e) {
	case 112, 39: // ERROR_DISK_FULL, ERROR_HANDLE_DISK_FULL
		return "abort-diskfull"
	case 19: // ERROR_WRITE_PROTECT
		return "abort-readonly"
	case 21, 1167: // ERROR_NOT_READY, ERROR_DEVICE_NOT_CONNECTED
		return "abort-notready"
	case 32, 33: // ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION
		return "retry"
	default:
		return "skip"
	}
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

// longPath returns the extended-length (\\?\) form of an absolute path so file
// operations bypass the legacy 260-char MAX_PATH limit, unconditionally. The
// path is cleaned first because \\?\ disables Win32 normalization.
func longPath(p string) string {
	if !filepath.IsAbs(p) || strings.HasPrefix(p, `\\?\`) {
		return p
	}
	p = filepath.Clean(p)
	if strings.HasPrefix(p, `\\`) { // UNC \\server\share -> \\?\UNC\server\share
		return `\\?\UNC\` + p[2:]
	}
	return `\\?\` + p
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
