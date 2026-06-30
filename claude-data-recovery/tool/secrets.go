package main

import (
	"encoding/json"
	"path/filepath"
	"regexp"
	"strings"
)

// sensitiveKey matches JSON object keys whose values are likely secrets and
// should be redacted (in `safe` and `redact-only` modes). Mirrors the spirit
// of SelfFork's audit secret-redaction.
var sensitiveKey = regexp.MustCompile(`(?i)(oauth|token|secret|passwd|password|api[_-]?key|(^|_)key$|credential|refresh|bearer|authorization|cookie|session[_-]?id|access[_-]?key)`)

// classifyAction decides what to do with a file given its base name and the
// chosen secrets mode. Returns one of:
//
//	copy         – copy verbatim
//	copy-secret  – copy verbatim but flag as secret (full mode)
//	redact       – copy with sensitive JSON keys redacted
//	quarantine   – copy into a segregated __SECRETS__ subtree (safe mode)
//	skip-secret  – do not copy at all (redact-only mode, live credentials)
func classifyAction(base, mode string) string {
	isCred := base == ".credentials.json" || base == "pipe.key"
	isRedactable := strings.HasPrefix(base, ".claude.json") ||
		base == "config.json" || base == ".mcp.json" ||
		base == "settings.json" || base == "settings.local.json"

	switch mode {
	case "full":
		if isCred || isRedactable {
			return "copy-secret"
		}
		return "copy"
	case "redact-only":
		if isCred {
			return "skip-secret"
		}
		if isRedactable {
			return "redact"
		}
		return "copy"
	default: // safe
		if isCred {
			return "quarantine"
		}
		if isRedactable {
			return "redact"
		}
		return "copy"
	}
}

// quarantineRel reroutes an output path from <host>/<user>/... to
// <host>/<user>/__SECRETS__/... so live credentials are segregated.
func quarantineRel(rel, host, user string) string {
	prefix := filepath.Join(host, user)
	tail := strings.TrimPrefix(rel, prefix+string(filepath.Separator))
	return filepath.Join(host, user, "__SECRETS__", tail)
}

// redactJSON parses data as JSON and replaces sensitive values with a marker.
// If the bytes are not valid JSON it returns them unchanged with ok=false.
func redactJSON(data []byte) (out []byte, ok bool) {
	var v any
	if err := json.Unmarshal(data, &v); err != nil {
		return data, false
	}
	redactValue(v)
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return data, false
	}
	return b, true
}

func redactValue(v any) {
	switch t := v.(type) {
	case map[string]any:
		for k, val := range t {
			if sensitiveKey.MatchString(k) {
				t[k] = "***REDACTED***"
				continue
			}
			redactValue(val)
		}
	case []any:
		for _, val := range t {
			redactValue(val)
		}
	}
}
