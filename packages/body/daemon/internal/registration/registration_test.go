package registration

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRegisterSuccess(t *testing.T) {
	var gotMethod, gotPath, gotContentType string
	var gotBody registerRequest

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		gotContentType = r.Header.Get("Content-Type")
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"auth_key":"0123456789abcdef0123456789abcdef"}`))
	}))
	defer srv.Close()

	res, err := Register(context.Background(), Config{
		OrchestratorURL: srv.URL,
		MachineID:       "work-ubuntu",
		Hostname:        "work-ubuntu.local",
		LocationTier:    "work",
		Version:         "0.5.0",
		Client:          srv.Client(),
	})
	if err != nil {
		t.Fatalf("Register returned error: %v", err)
	}
	if res.AlreadyRegistered {
		t.Errorf("AlreadyRegistered = true, want false")
	}
	if res.AuthKey != "0123456789abcdef0123456789abcdef" {
		t.Errorf("AuthKey = %q, want the server-issued key", res.AuthKey)
	}
	if gotMethod != http.MethodPost {
		t.Errorf("method = %q, want POST", gotMethod)
	}
	if gotPath != "/api/fleet/register" {
		t.Errorf("path = %q, want /api/fleet/register", gotPath)
	}
	if gotContentType != "application/json" {
		t.Errorf("content-type = %q, want application/json", gotContentType)
	}
	if gotBody.MachineID != "work-ubuntu" || gotBody.Hostname != "work-ubuntu.local" ||
		gotBody.LocationTier != "work" || gotBody.Version != "0.5.0" {
		t.Errorf("request body = %+v, missing expected fields", gotBody)
	}
}

func TestRegisterDefaultsLocationTierAndHostname(t *testing.T) {
	var gotBody registerRequest
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"auth_key":"0123456789abcdef0123456789abcdef"}`))
	}))
	defer srv.Close()

	if _, err := Register(context.Background(), Config{
		OrchestratorURL: srv.URL,
		MachineID:       "host-a",
		Version:         "0.5.0",
		Client:          srv.Client(),
	}); err != nil {
		t.Fatalf("Register returned error: %v", err)
	}
	if gotBody.LocationTier != "auto" {
		t.Errorf("location_tier = %q, want default auto", gotBody.LocationTier)
	}
	if gotBody.Hostname != "host-a" {
		t.Errorf("hostname = %q, want fallback to machine_id", gotBody.Hostname)
	}
}

func TestRegisterAlreadyRegistered(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusConflict)
		_, _ = w.Write([]byte(`{"detail":"machine_id 'm' already registered"}`))
	}))
	defer srv.Close()

	res, err := Register(context.Background(), Config{
		OrchestratorURL: srv.URL,
		MachineID:       "m",
		Hostname:        "h",
		Version:         "0.5.0",
		Client:          srv.Client(),
	})
	if err != nil {
		t.Fatalf("Register on 409 returned error: %v, want nil (idempotent)", err)
	}
	if !res.AlreadyRegistered {
		t.Errorf("AlreadyRegistered = false, want true on HTTP 409")
	}
	if res.AuthKey != "" {
		t.Errorf("AuthKey = %q, want empty on 409", res.AuthKey)
	}
}

func TestRegisterServerErrorIsTyped(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("boom"))
	}))
	defer srv.Close()

	_, err := Register(context.Background(), Config{
		OrchestratorURL: srv.URL,
		MachineID:       "m",
		Hostname:        "h",
		Version:         "0.5.0",
		Client:          srv.Client(),
	})
	if err == nil {
		t.Fatal("Register on 500 returned nil error, want *StatusError")
	}
	var se *StatusError
	if !errors.As(err, &se) {
		t.Fatalf("error = %v, want *StatusError", err)
	}
	if se.StatusCode != http.StatusInternalServerError {
		t.Errorf("StatusCode = %d, want 500", se.StatusCode)
	}
	if se.Body != "boom" {
		t.Errorf("Body = %q, want boom", se.Body)
	}
}

func TestRegisterNetworkErrorIsNotTyped(t *testing.T) {
	// Start then immediately close a server to obtain an unreachable URL.
	srv := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	url := srv.URL
	client := srv.Client()
	srv.Close()

	_, err := Register(context.Background(), Config{
		OrchestratorURL: url,
		MachineID:       "m",
		Hostname:        "h",
		Version:         "0.5.0",
		Client:          client,
	})
	if err == nil {
		t.Fatal("Register against a closed server returned nil error")
	}
	var se *StatusError
	if errors.As(err, &se) {
		t.Errorf("transport failure classified as *StatusError: %v", err)
	}
}

func TestRegisterWithRetrySucceedsFirstTry(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"auth_key":"0123456789abcdef0123456789abcdef"}`))
	}))
	defer srv.Close()

	res, err := RegisterWithRetry(context.Background(), Config{
		OrchestratorURL: srv.URL,
		MachineID:       "m",
		Hostname:        "h",
		Version:         "0.5.0",
		Client:          srv.Client(),
	}, nil)
	if err != nil {
		t.Fatalf("RegisterWithRetry returned error: %v", err)
	}
	if res.AuthKey != "0123456789abcdef0123456789abcdef" {
		t.Errorf("AuthKey = %q, want the server-issued key", res.AuthKey)
	}
}

func TestRegisterWithRetryStopsOnCancelledContext(t *testing.T) {
	// A closed server forces Register to fail; a cancelled context must make
	// RegisterWithRetry return promptly rather than loop forever.
	srv := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	url := srv.URL
	client := srv.Client()
	srv.Close()

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := RegisterWithRetry(ctx, Config{
		OrchestratorURL: url,
		MachineID:       "m",
		Hostname:        "h",
		Version:         "0.5.0",
		Client:          client,
	}, nil)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("err = %v, want context.Canceled", err)
	}
}
