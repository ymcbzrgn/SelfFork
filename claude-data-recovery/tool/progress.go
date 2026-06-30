package main

import (
	"fmt"
	"io"
	"strings"
	"sync/atomic"
	"time"
)

// Progress renders a single repainting line: a percentage bar driven by bytes
// copied / total bytes, plus throughput, ETA and the current file. The total is
// known up front from the discovery (sizing) pass, so the percentage is honest.
type Progress struct {
	total int64
	done  int64 // updated atomically
	cur   atomic.Value
	start time.Time
	stop  chan struct{}
}

func newProgress(total int64) *Progress {
	p := &Progress{total: total, start: time.Now(), stop: make(chan struct{})}
	p.cur.Store("")
	return p
}

func (p *Progress) run() {
	go func() {
		t := time.NewTicker(120 * time.Millisecond)
		defer t.Stop()
		for {
			select {
			case <-p.stop:
				return
			case <-t.C:
				p.render()
			}
		}
	}()
}

func (p *Progress) finish() {
	close(p.stop)
	p.render()
	fmt.Println()
}

func (p *Progress) setCur(s string)   { p.cur.Store(s) }
func (p *Progress) add(n int64)        { atomic.AddInt64(&p.done, n) }
func (p *Progress) writer() io.Writer  { return counterWriter{p} }

type counterWriter struct{ p *Progress }

func (c counterWriter) Write(b []byte) (int, error) {
	atomic.AddInt64(&c.p.done, int64(len(b)))
	return len(b), nil
}

func (p *Progress) render() {
	done := atomic.LoadInt64(&p.done)
	total := p.total

	var pct float64
	if total > 0 {
		pct = float64(done) / float64(total) * 100
	}
	if pct > 100 {
		pct = 100
	}

	const w = 30
	filled := int(pct / 100 * float64(w))
	if filled > w {
		filled = w
	}
	if filled < 0 {
		filled = 0
	}
	bar := strings.Repeat("█", filled) + strings.Repeat("░", w-filled)

	el := time.Since(p.start).Seconds()
	if el <= 0 {
		el = 0.001
	}
	spd := float64(done) / 1e6 / el // MB/s

	eta := "--:--"
	if done > 0 && total > done {
		rate := float64(done) / el
		if rate > 0 {
			eta = fmtDur(float64(total-done) / rate)
		}
	}

	cur := ""
	if v, ok := p.cur.Load().(string); ok {
		cur = shorten(v, 46)
	}

	// \033[K clears to end of line so shorter lines don't leave stale chars.
	fmt.Printf("\r  [%s] %5.1f%%  %s / %s  %4.0f MB/s  ETA %s  %s\033[K",
		bar, pct, human(done), human(total), spd, eta, cur)
}
