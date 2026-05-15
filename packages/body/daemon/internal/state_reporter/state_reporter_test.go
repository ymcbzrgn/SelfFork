package state_reporter

import (
	"crypto/sha256"
	"encoding/hex"
	"testing"
)

func TestHashBytesIsStableSha256(t *testing.T) {
	data := []byte(`{"k":"v"}`)
	want := sha256.Sum256(data)
	got := hashBytes(data)
	if got != hex.EncodeToString(want[:]) {
		t.Errorf("hashBytes mismatch: got %s want %s", got, hex.EncodeToString(want[:]))
	}
}
