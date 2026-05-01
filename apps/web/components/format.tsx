"use client";

import { useEffect, useState } from "react";

function _formatRelativeAge(isoTs: string, now: Date): string {
  const then = new Date(isoTs).getTime();
  const diffSec = Math.floor((now.getTime() - then) / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

function _formatRelativeFuture(isoTs: string, now: Date): string {
  const then = new Date(isoTs).getTime();
  const diffSec = Math.floor((then - now.getTime()) / 1000);
  if (diffSec <= 0) return "now";
  if (diffSec < 60) return `in ${diffSec}s`;
  if (diffSec < 3600) return `in ${Math.floor(diffSec / 60)}m`;
  if (diffSec < 86400) return `in ${Math.floor(diffSec / 3600)}h`;
  return `in ${Math.floor(diffSec / 86400)}d`;
}

export function RelativeAge({ isoTs }: { isoTs: string }) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  if (now === null) return <span className="font-mono text-xs">…</span>;
  return (
    <span title={isoTs} className="font-mono text-xs">
      {_formatRelativeAge(isoTs, now)}
    </span>
  );
}

export function RelativeFuture({ isoTs }: { isoTs: string }) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  if (now === null) return <span className="font-mono text-xs">…</span>;
  return (
    <span title={isoTs} className="font-mono text-xs">
      {_formatRelativeFuture(isoTs, now)}
    </span>
  );
}

export function ShortSessionId({ id }: { id: string }) {
  return (
    <span title={id} className="font-mono text-xs">
      {id.slice(0, 8)}…{id.slice(-4)}
    </span>
  );
}
