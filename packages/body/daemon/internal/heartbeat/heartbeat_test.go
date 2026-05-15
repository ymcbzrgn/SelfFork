package heartbeat

import "testing"
import "time"

func TestNextBackoffSequence(t *testing.T) {
	cases := []struct {
		in   time.Duration
		want time.Duration
	}{
		{0, time.Second},
		{time.Second, 2 * time.Second},
		{2 * time.Second, 5 * time.Second},
		{5 * time.Second, 15 * time.Second},
		{15 * time.Second, 30 * time.Second},
		{30 * time.Second, 60 * time.Second},
		{60 * time.Second, 60 * time.Second},
		{120 * time.Second, 60 * time.Second},
	}
	for _, c := range cases {
		got := NextBackoff(c.in)
		if got != c.want {
			t.Errorf("NextBackoff(%v) = %v, want %v", c.in, got, c.want)
		}
	}
}
