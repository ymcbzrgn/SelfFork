package main

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// Item is one file selected for collection.
type Item struct {
	Src    string // absolute source path
	Rel    string // path under the output root
	Kind   string // global | global-mem | project-claude | project-CLAUDE.md | ...
	Action string // copy | copy-secret | redact | quarantine | skip-secret
	Size   int64
	Secret bool
}

// Result is an Item after the copy phase (or after planning, in dry-run).
type Result struct {
	Item
	Hash   string
	Status string
	OutRel string
}

// Plan is the full set of items discovered, plus diagnostics.
type Plan struct {
	Items      []Item
	TotalBytes int64
	Excluded   []string
	Log        []string
}

func (p *Plan) add(it Item) {
	p.Items = append(p.Items, it)
	if it.Action != "skip-secret" {
		p.TotalBytes += it.Size
	}
}

func (p *Plan) addExcluded(path, reason string) {
	p.Excluded = append(p.Excluded, path+"\t"+reason)
}

func (p *Plan) logf(format string, a ...any) {
	p.Log = append(p.Log, fmt.Sprintf(format, a...))
}

type profile struct {
	user string
	home string
}

func homeDir() string {
	if h, err := os.UserHomeDir(); err == nil && h != "" {
		return h
	}
	if up := os.Getenv("USERPROFILE"); up != "" {
		return up
	}
	return "."
}

func currentUser() string {
	u := filepath.Base(homeDir())
	if u == "" || u == "." {
		return "current-user"
	}
	return u
}

func resolveConfigDir(home string) string {
	if strings.EqualFold(home, homeDir()) {
		if env := os.Getenv("CLAUDE_CONFIG_DIR"); env != "" {
			return env
		}
	}
	return filepath.Join(home, ".claude")
}

// targetProfiles returns the user profiles to collect. Default: the current
// user only. With --all-users: every profile under C:\Users that has Claude data.
func targetProfiles(cfg *Config) []profile {
	cur := profile{user: currentUser(), home: homeDir()}
	if !cfg.AllUsers {
		return []profile{cur}
	}
	root := userProfilesRoot()
	entries, err := os.ReadDir(root)
	if err != nil {
		return []profile{cur}
	}
	skip := map[string]bool{"all users": true, "default": true, "default user": true, "public": true}
	var out []profile
	for _, e := range entries {
		if !e.IsDir() || skip[strings.ToLower(e.Name())] {
			continue
		}
		home := filepath.Join(root, e.Name())
		_, c1 := os.Stat(filepath.Join(home, ".claude"))
		_, c2 := os.Stat(filepath.Join(home, ".claude.json"))
		if c1 == nil || c2 == nil {
			out = append(out, profile{user: e.Name(), home: home})
		}
	}
	found := false
	for _, p := range out {
		if strings.EqualFold(p.home, cur.home) {
			found = true
		}
	}
	if !found {
		out = append([]profile{cur}, out...)
	}
	if len(out) == 0 {
		return []profile{cur}
	}
	return out
}

// buildPlan discovers every item to collect: Layer A (per-user global store)
// for each target profile, then Layer B (all-drives project sweep).
func buildPlan(cfg *Config, host string) *Plan {
	p := &Plan{}
	globalSkip := map[string]bool{}
	profiles := targetProfiles(cfg)

	for _, pf := range profiles {
		p.logf("profile: %s (home=%s)", pf.user, pf.home)

		userDir := resolveConfigDir(pf.home)
		if st, err := os.Stat(userDir); err == nil && st.IsDir() {
			globalSkip[keyPath(userDir)] = true
			collectTree(userDir, filepath.Join(host, pf.user, "global", ".claude"), "global", cfg, host, pf.user, p)
		} else {
			p.logf("  no .claude dir at %s", userDir)
		}

		if matches, _ := filepath.Glob(filepath.Join(pf.home, ".claude.json*")); len(matches) > 0 {
			for _, m := range matches {
				globalSkip[keyPath(m)] = true
				addSingleFile(m, filepath.Join(host, pf.user, "global", filepath.Base(m)), "claude.json", cfg, host, pf.user, p)
			}
		}

		mem := filepath.Join(pf.home, ".claude-mem")
		if st, err := os.Stat(mem); err == nil && st.IsDir() {
			globalSkip[keyPath(mem)] = true
			collectTree(mem, filepath.Join(host, pf.user, "global", ".claude-mem"), "global-mem", cfg, host, pf.user, p)
		}
	}

	// Machine-wide (non-per-user) Claude locations: enterprise managed settings.
	collectMachineLevel(cfg, host, p)

	// Project artifacts are attributed to the primary (current) profile label;
	// their original absolute path is preserved under by-drive/ for provenance.
	primary := profiles[0]
	sweepDrives(cfg, host, primary.user, p, globalSkip)
	return p
}

// collectMachineLevel grabs machine-scope Claude dirs (managed-settings, etc.)
// that live outside any user profile.
func collectMachineLevel(cfg *Config, host string, p *Plan) {
	for _, d := range machineClaudeDirs() {
		if st, err := os.Stat(d); err == nil && st.IsDir() {
			p.logf("machine-level: %s", d)
			collectTree(d, relForSource(host, "_machine", d), "machine", cfg, host, "_machine", p)
		}
	}
}

// collectTree adds every regular file under root, mapping it to relBase + its
// path relative to root. Reparse points are not followed.
func collectTree(root, relBase, kind string, cfg *Config, host, user string, p *Plan) {
	_ = filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			p.addExcluded(path, "access: "+err.Error())
			if d != nil && d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if d.IsDir() {
			if info, ie := d.Info(); ie == nil && isReparsePoint(info) {
				p.addExcluded(path, "reparse-point (not followed)")
				return filepath.SkipDir
			}
			return nil
		}
		if !d.Type().IsRegular() {
			return nil
		}
		if cfg.Lean && leanSkip(path) {
			return nil
		}
		info, ie := d.Info()
		if ie != nil {
			p.addExcluded(path, "stat: "+ie.Error())
			return nil
		}
		rel, rerr := filepath.Rel(root, path)
		if rerr != nil {
			rel = filepath.Base(path)
		}
		addClassified(path, filepath.Join(relBase, rel), kind, info.Size(), cfg, host, user, p)
		return nil
	})
}

func addSingleFile(src, rel, kind string, cfg *Config, host, user string, p *Plan) {
	info, err := os.Stat(src)
	if err != nil {
		p.addExcluded(src, "stat: "+err.Error())
		return
	}
	addClassified(src, rel, kind, info.Size(), cfg, host, user, p)
}

func addClassified(src, rel, kind string, size int64, cfg *Config, host, user string, p *Plan) {
	base := filepath.Base(src)
	action := classifyAction(base, cfg.Secrets)
	secret := action == "quarantine" || action == "copy-secret" || action == "skip-secret"
	if action == "quarantine" {
		rel = quarantineRel(rel, host, user)
	}
	p.add(Item{Src: src, Rel: rel, Kind: kind, Action: action, Size: size, Secret: secret})
}

// relForSource maps an absolute source path to its output location under
// by-drive/<letter>/<original path>, preserving provenance and avoiding
// collisions between identically-named files from different repos.
func relForSource(host, user, abs string) string {
	vol := filepath.VolumeName(abs) // "C:" on Windows, "" on POSIX
	letter := strings.TrimSuffix(vol, ":")
	if letter == "" {
		letter = "root"
	}
	rest := strings.TrimPrefix(abs[len(vol):], string(filepath.Separator))
	return filepath.Join(host, user, "by-drive", letter, rest)
}

func leanSkip(path string) bool {
	l := strings.ToLower(path)
	return strings.Contains(l, string(filepath.Separator)+".claude"+string(filepath.Separator)+"plugins"+string(filepath.Separator)) ||
		strings.Contains(l, string(filepath.Separator)+".claude-mem"+string(filepath.Separator)+"chroma"+string(filepath.Separator)) ||
		strings.Contains(l, string(filepath.Separator)+".claude-mem"+string(filepath.Separator)+"logs"+string(filepath.Separator))
}

func defaultPruneNames() map[string]bool {
	names := []string{
		"node_modules", ".git", ".next", ".nuxt", "dist", "build", "out",
		"__pycache__", ".venv", "venv", ".tox", "target", ".gradle", ".m2",
		".cargo", ".idea", ".vs", ".svn", ".hg", ".pytest_cache", ".mypy_cache",
		".ruff_cache",
	}
	m := make(map[string]bool, len(names))
	for _, n := range names {
		m[n] = true
	}
	return m
}

// isSystemPrune reports whether a top-level system directory on a volume should
// be skipped in default (non-exhaustive) mode.
func isSystemPrune(path, root string) bool {
	rel := strings.ToLower(strings.TrimPrefix(keyPath(path), keyPath(root)))
	rel = strings.TrimPrefix(rel, string(filepath.Separator))
	switch rel {
	case "windows", "$recycle.bin", "system volume information", "programdata",
		"recovery", "perflogs",
		"users" + string(filepath.Separator) + "all users",
		"users" + string(filepath.Separator) + "default",
		"users" + string(filepath.Separator) + "default user":
		return true
	}
	return false
}

func sweepDrives(cfg *Config, host, user string, p *Plan, globalSkip map[string]bool) {
	roots := cfg.Roots
	if len(roots) == 0 {
		roots = listVolumes(cfg.IncludeRemovable)
	}
	prune := defaultPruneNames()
	for _, root := range roots {
		if sameOrUnder(root, cfg.OutDir) {
			p.logf("skip sweep root %s (holds the output dir)", root)
			continue
		}
		p.logf("sweeping %s", root)
		sweepOne(root, cfg, host, user, p, globalSkip, prune)
	}
}

func sweepOne(root string, cfg *Config, host, user string, p *Plan, globalSkip, prune map[string]bool) {
	_ = filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			p.addExcluded(path, "access: "+err.Error())
			if d != nil && d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if sameOrUnder(path, cfg.OutDir) {
			return filepath.SkipDir
		}
		if d.IsDir() {
			if info, ie := d.Info(); ie == nil && isReparsePoint(info) {
				p.addExcluded(path, "reparse-point (not followed)")
				return filepath.SkipDir
			}
			if globalSkip[keyPath(path)] {
				return filepath.SkipDir // already collected via the global store
			}
			name := d.Name()
			if name == ".claude" {
				collectTree(path, relForSource(host, user, path), "project-claude", cfg, host, user, p)
				return filepath.SkipDir
			}
			if !cfg.Exhaustive {
				if prune[strings.ToLower(name)] || isSystemPrune(path, root) {
					return filepath.SkipDir
				}
			}
			return nil
		}
		base := d.Name()
		if base == "CLAUDE.md" || base == "CLAUDE.local.md" || base == ".mcp.json" || base == ".claude.json" {
			if globalSkip[keyPath(path)] {
				return nil
			}
			var size int64
			if info, ie := d.Info(); ie == nil {
				size = info.Size()
			}
			addClassified(path, relForSource(host, user, path), "project-"+base, size, cfg, host, user, p)
		}
		return nil
	})
}

func planResults(plan *Plan) []Result {
	res := make([]Result, 0, len(plan.Items))
	for _, it := range plan.Items {
		st := "planned"
		if it.Action == "skip-secret" {
			st = "planned-skip-secret"
		}
		res = append(res, Result{Item: it, Status: st, OutRel: it.Rel})
	}
	return res
}
