package command_intake

import (
	"testing"
	"time"
)

func TestVerifyAuthenticPayload(t *testing.T) {
	i := &Intake{Secret: "sshhh"}
	args := map[string]interface{}{"keys": "ls", "target": "dev:0"}
	now := time.Now().UTC()
	ts := now.Format(time.RFC3339)
	sig := i.Sign("send_keys", args, "n1", ts)

	cmd := SignedCommand{
		Command:   "send_keys",
		Args:      args,
		Nonce:     "n1",
		Timestamp: ts,
		Signature: sig,
	}
	if err := i.Verify(cmd, now); err != nil {
		t.Fatalf("Verify failed: %v", err)
	}
}

func TestVerifyRejectsTamperedSignature(t *testing.T) {
	i := &Intake{Secret: "sshhh"}
	now := time.Now().UTC()
	ts := now.Format(time.RFC3339)
	sig := i.Sign("send_keys", map[string]interface{}{}, "n1", ts)
	// Flip last byte
	tampered := sig[:len(sig)-1] + "0"

	cmd := SignedCommand{
		Command:   "send_keys",
		Args:      map[string]interface{}{},
		Nonce:     "n1",
		Timestamp: ts,
		Signature: tampered,
	}
	if err := i.Verify(cmd, now); err == nil {
		t.Fatal("expected signature mismatch error")
	}
}

func TestVerifyRejectsClockSkew(t *testing.T) {
	i := &Intake{Secret: "sshhh", MaxClockSkew: 10 * time.Second}
	stale := time.Now().Add(-5 * time.Minute).UTC()
	ts := stale.Format(time.RFC3339)
	sig := i.Sign("send_keys", map[string]interface{}{}, "n1", ts)

	cmd := SignedCommand{
		Command:   "send_keys",
		Args:      map[string]interface{}{},
		Nonce:     "n1",
		Timestamp: ts,
		Signature: sig,
	}
	if err := i.Verify(cmd, time.Now().UTC()); err == nil {
		t.Fatal("expected skew error")
	}
}

func TestVerifyRejectsMissingNonce(t *testing.T) {
	i := &Intake{Secret: "sshhh"}
	cmd := SignedCommand{
		Command:   "x",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Signature: "00",
	}
	if err := i.Verify(cmd, time.Now().UTC()); err == nil {
		t.Fatal("expected missing nonce error")
	}
}
