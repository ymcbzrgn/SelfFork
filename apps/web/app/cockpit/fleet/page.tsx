/**
 * Cockpit Fleet view (M5 — ADR-005 §M5-A).
 *
 * Lists registered body daemons; surface heartbeat status, latency, location
 * tier, and snapper CLI presence. The location-aware slider in the Mission
 * tab pulls from `fleetCurrentMachineId` so switching the active machine
 * here adjusts the mission threshold automatically.
 */
"use client";

import { useEffect } from "react";

import { useCockpitStore, type DaemonView } from "@/lib/store";

function StatusDot({ online }: { online: boolean }) {
  return (
    <span
      aria-label={online ? "online" : "offline"}
      className={`inline-block w-2.5 h-2.5 rounded-full ${
        online ? "bg-green-500" : "bg-zinc-400"
      }`}
    />
  );
}

function FleetRow({ daemon }: { daemon: DaemonView }) {
  const setCurrent = useCockpitStore((s) => s.setFleetCurrentMachine);
  const current = useCockpitStore((s) => s.fleetCurrentMachineId);
  const isCurrent = current === daemon.machine_id;
  return (
    <tr
      className={`border-b ${isCurrent ? "bg-amber-50 dark:bg-amber-950/30" : ""}`}
      data-testid={`fleet-row-${daemon.machine_id}`}
    >
      <td className="px-3 py-2 font-mono text-sm">{daemon.machine_id}</td>
      <td className="px-3 py-2">{daemon.hostname}</td>
      <td className="px-3 py-2">
        <StatusDot online={daemon.online} />
        <span className="ml-2 text-xs text-zinc-500">
          {daemon.online ? "online" : "offline"}
        </span>
      </td>
      <td className="px-3 py-2">
        {daemon.latency_ms != null ? `${daemon.latency_ms} ms` : "—"}
      </td>
      <td className="px-3 py-2">{daemon.location_tier}</td>
      <td className="px-3 py-2">{daemon.snapper_clis.join(", ") || "—"}</td>
      <td className="px-3 py-2 font-mono text-xs">{daemon.version}</td>
      <td className="px-3 py-2">
        <button
          type="button"
          className={`text-sm rounded px-2 py-1 ${
            isCurrent
              ? "bg-amber-200 text-amber-950"
              : "bg-zinc-100 hover:bg-zinc-200"
          }`}
          onClick={() => setCurrent(isCurrent ? null : daemon.machine_id)}
        >
          {isCurrent ? "Active" : "Set active"}
        </button>
      </td>
    </tr>
  );
}

export default function FleetPage() {
  const daemons = useCockpitStore((s) => s.fleetDaemons);
  const setDaemons = useCockpitStore((s) => s.setFleetDaemons);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/fleet/daemons")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data: DaemonView[]) => {
        if (!cancelled) setDaemons(data);
      })
      .catch(() => {
        // Backend not reachable yet — leave the table empty; the Mission tab
        // continues to work with mock state.
      });
    return () => {
      cancelled = true;
    };
  }, [setDaemons]);

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Fleet</h1>
      <p className="text-sm text-zinc-500">
        Body daemons registered with this orchestrator. Setting one as active
        shifts the Mission tab&apos;s location-aware threshold to that
        machine&apos;s tier.
      </p>
      {daemons.length === 0 ? (
        <div className="text-sm text-zinc-500">
          No daemons registered yet. Run{" "}
          <code>selffork-daemon register --machine-id …</code> on a remote host
          to enroll one.
        </div>
      ) : (
        <table className="w-full text-left">
          <thead className="border-b">
            <tr>
              <th className="px-3 py-2">Machine</th>
              <th className="px-3 py-2">Hostname</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Latency</th>
              <th className="px-3 py-2">Tier</th>
              <th className="px-3 py-2">CLIs</th>
              <th className="px-3 py-2">Version</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {daemons.map((daemon) => (
              <FleetRow key={daemon.machine_id} daemon={daemon} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
