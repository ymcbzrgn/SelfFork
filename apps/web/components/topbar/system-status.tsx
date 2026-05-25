/**
 * System-status drawer (S8 — ADR-007 §4 S8). Topbar ServerCog opens it.
 *
 * Fetches live health for the dashboard API, the model endpoint, the
 * autonomy heartbeat, the Telegram bridge, and the CodexBar quota sidecar
 * each time it opens. No-mock: a service that can't be reached shows an
 * honest "Offline" / "Unknown" row, never a fabricated green.
 */
"use client";

import { useEffect, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  getCodexBarStatus,
  getHealth,
  getHeartbeatState,
  getModelEndpoint,
  getTelegramStatus,
} from "@/lib/api";

type Dot = "green" | "amber" | "red" | "gray";

interface Row {
  label: string;
  state: string;
  dot: Dot;
}

function StatusDot({ dot }: { dot: Dot }) {
  const cls =
    dot === "green"
      ? "bg-success"
      : dot === "amber"
        ? "bg-amber-500"
        : dot === "red"
          ? "bg-error"
          : "bg-on-surface-variant/40";
  return <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${cls}`} aria-hidden />;
}

export function SystemStatusSheet({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const [rows, setRows] = useState<Row[] | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setRows(null);

    // Fetch all services concurrently — each chain resolves to a Row and
    // never rejects (its own .catch yields an honest Offline/Unknown), so
    // the drawer fills in one round-trip instead of five sequential waits.
    const load = async () => {
      const [api, model, heartbeat, telegram, codexbar] = await Promise.all([
        getHealth()
          .then(
            (h): Row => ({
              label: "Dashboard API",
              state: h.status === "ok" ? "Online" : h.status,
              dot: h.status === "ok" ? "green" : "amber",
            }),
          )
          .catch(
            (): Row => ({ label: "Dashboard API", state: "Offline", dot: "red" }),
          ),
        getModelEndpoint()
          .then(
            (m): Row => ({
              label: "Model endpoint",
              state: m.url
                ? `${m.model_name || "—"} @ ${m.url}`
                : "Not configured",
              dot: m.url ? "green" : "gray",
            }),
          )
          .catch(
            (): Row => ({ label: "Model endpoint", state: "Unknown", dot: "gray" }),
          ),
        getHeartbeatState()
          .then(
            (hb): Row => ({
              label: "Heartbeat (autonomy)",
              state: hb.is_running
                ? `Running · tick ${hb.tick_count}`
                : `Stopped (${hb.state})`,
              dot: hb.is_running ? "green" : "gray",
            }),
          )
          .catch(
            (): Row => ({
              label: "Heartbeat (autonomy)",
              state: "Unknown",
              dot: "gray",
            }),
          ),
        getTelegramStatus()
          .then((tg): Row => {
            const dot: Dot =
              tg.state === "connected"
                ? "green"
                : tg.state === "errored"
                  ? "red"
                  : "gray";
            const state =
              tg.state === "connected"
                ? `Connected${tg.bot_username ? ` (@${tg.bot_username})` : ""}`
                : tg.state === "not_configured"
                  ? "Not configured"
                  : "Error";
            return { label: "Telegram bridge", state, dot };
          })
          .catch(
            (): Row => ({ label: "Telegram bridge", state: "Unknown", dot: "gray" }),
          ),
        getCodexBarStatus()
          .then((cb): Row => {
            const dot: Dot =
              cb.state === "running"
                ? "green"
                : cb.state === "disabled"
                  ? "gray"
                  : "amber";
            return { label: "CodexBar (quota source)", state: cb.state, dot };
          })
          .catch(
            (): Row => ({
              label: "CodexBar (quota source)",
              state: "Unknown",
              dot: "gray",
            }),
          ),
      ]);
      if (!cancelled) setRows([api, model, heartbeat, telegram, codexbar]);
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [open]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="bg-surface text-on-surface border-outline-variant">
        <SheetHeader>
          <SheetTitle className="text-on-surface">System status</SheetTitle>
          <SheetDescription className="text-on-surface-variant">
            Live health across the dashboard, model endpoint, autonomy loop,
            and the CLI support services.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-2">
          {rows === null ? (
            <p className="py-4 text-caption text-on-surface-variant">Checking…</p>
          ) : (
            rows.map((r) => (
              <div
                key={r.label}
                className="flex items-center justify-between gap-3 border-b border-outline-variant/20 py-3"
              >
                <span className="flex items-center gap-2 text-caption font-medium text-on-surface">
                  <StatusDot dot={r.dot} />
                  {r.label}
                </span>
                <span className="max-w-[55%] truncate text-right font-mono text-[11px] text-on-surface-variant">
                  {r.state}
                </span>
              </div>
            ))
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
