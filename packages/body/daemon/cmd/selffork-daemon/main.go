// Package main is the entry point for the SelfFork body daemon.
//
// The daemon runs on remote machines (work Windows / Ubuntu) and extends the
// home orchestrator's reach via Tailscale. It reports local CLI state via
// the M3 snapper file format and accepts signed prompts back from the home
// orchestrator over a WebSocket channel.
//
// See: docs/decisions/ADR-005_M5_Body.md §M5-A.
package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github.com/spf13/cobra"

	"github.com/selffork/selffork-daemon/internal/cli_bridge"
	"github.com/selffork/selffork-daemon/internal/command_intake"
	"github.com/selffork/selffork-daemon/internal/heartbeat"
	"github.com/selffork/selffork-daemon/internal/registration"
	"github.com/selffork/selffork-daemon/internal/state_reporter"
)

// Version is overridden at link-time via -ldflags.
var Version = "0.0.0-dev"

func main() {
	rootCmd := &cobra.Command{
		Use:     "selffork-daemon",
		Short:   "SelfFork body daemon: extends home brain to remote machines via Tailscale",
		Version: Version,
		RunE:    runDaemon,
	}

	rootCmd.Flags().String("orchestrator-url", "", "Home orchestrator WebSocket URL (Tailscale)")
	rootCmd.Flags().String("machine-id", "", "Daemon machine identifier (auto-derived from hostname when empty)")
	rootCmd.Flags().String("location-tier", "auto", "Location tier: home | work | auto")
	rootCmd.Flags().Duration("heartbeat-interval", 15*time.Second, "Heartbeat cadence")
	rootCmd.Flags().Duration("state-report-interval", time.Second, "CLI state poll interval (M3 snapper format)")
	rootCmd.Flags().String("snapper-root", "", "Root directory of CLI snapper state files (default ~/.selffork/cli-state)")
	rootCmd.Flags().String("registration-secret", "", "HMAC-SHA256 shared secret for signed payloads (env: SELFFORK_DAEMON_SECRET)")

	if err := rootCmd.Execute(); err != nil {
		log.Fatal(err)
	}
}

func runDaemon(cmd *cobra.Command, _ []string) error {
	orchURL, _ := cmd.Flags().GetString("orchestrator-url")
	if orchURL == "" {
		return errors.New("--orchestrator-url is required")
	}
	machineID, _ := cmd.Flags().GetString("machine-id")
	if machineID == "" {
		host, err := os.Hostname()
		if err != nil {
			return fmt.Errorf("derive machine-id: %w", err)
		}
		machineID = host
	}
	locationTier, _ := cmd.Flags().GetString("location-tier")
	heartbeatInterval, _ := cmd.Flags().GetDuration("heartbeat-interval")
	stateReportInterval, _ := cmd.Flags().GetDuration("state-report-interval")
	snapperRoot, _ := cmd.Flags().GetString("snapper-root")
	secret, _ := cmd.Flags().GetString("registration-secret")
	if secret == "" {
		secret = os.Getenv("SELFFORK_DAEMON_SECRET")
	}
	if secret == "" {
		return errors.New("--registration-secret or SELFFORK_DAEMON_SECRET env required")
	}

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	// Self-register with the orchestrator's fleet registry BEFORE starting the
	// heartbeat/state/intake goroutines. The server keys heartbeat and state
	// ingest on the machine_id already existing in its registry (unknown
	// machines get HTTP 404), so an unregistered daemon would 404 on its very
	// first heartbeat. RegisterWithRetry mirrors the heartbeat resilience
	// policy: it retries a transiently-unreachable orchestrator with backoff
	// rather than aborting, and returns only once registered (HTTP 201), when
	// the machine is already known (HTTP 409, treated as idempotent success),
	// or when ctx is cancelled by a shutdown signal.
	hostname, err := os.Hostname()
	if err != nil {
		hostname = machineID
	}
	regResult, err := registration.RegisterWithRetry(ctx, registration.Config{
		OrchestratorURL: orchURL,
		MachineID:       machineID,
		Hostname:        hostname,
		LocationTier:    locationTier,
		Version:         Version,
	}, log.Printf)
	if err != nil {
		// ctx was cancelled (shutdown signal) before registration completed.
		return nil
	}
	if regResult.AlreadyRegistered {
		log.Printf("fleet registration: machine %q already registered, continuing", machineID)
	} else {
		// The auth_key is issued for future authenticated ingest; today's
		// heartbeat/state endpoints authorise purely on the registered
		// machine_id, so it is not threaded into their wire payloads.
		log.Printf("fleet registration: machine %q registered (auth_key issued, %d chars)", machineID, len(regResult.AuthKey))
	}

	hb := &heartbeat.Heartbeat{
		OrchestratorURL: orchURL,
		MachineID:       machineID,
		LocationTier:    locationTier,
		Version:         Version,
		Interval:        heartbeatInterval,
	}
	go func() {
		if err := hb.Run(ctx); err != nil {
			log.Printf("heartbeat exit: %v", err)
		}
	}()

	// Select the platform CLI bridge: PowerShell job control on Windows, tmux
	// elsewhere. Both satisfy the cli_bridge.Bridge contract.
	var bridge cli_bridge.Bridge
	if runtime.GOOS == "windows" {
		bridge = cli_bridge.NewWindowsBridge()
	} else {
		bridge = cli_bridge.NewTmuxBridge()
	}
	reporter := &state_reporter.Reporter{
		OrchestratorURL: orchURL,
		MachineID:       machineID,
		SnapperRoot:     snapperRoot,
		Interval:        stateReportInterval,
	}
	go func() {
		if err := reporter.Run(ctx); err != nil {
			log.Printf("state reporter exit: %v", err)
		}
	}()

	intake := &command_intake.Intake{
		OrchestratorURL: orchURL,
		MachineID:       machineID,
		Secret:          secret,
		Bridge:          bridge,
	}
	go func() {
		if err := intake.Run(ctx); err != nil {
			log.Printf("command intake exit: %v", err)
		}
	}()

	<-ctx.Done()
	return nil
}
