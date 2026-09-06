"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

export function ServiceNode({ data }: NodeProps) {
  const health = (data as { health?: string; label?: string }).health || "unknown";
  const label = (data as { label?: string }).label;
  const color =
    health === "healthy" ? "#3fb950" : health === "unhealthy" ? "#f85149" : "#d29922";
  return (
    <div className="rounded-lg border border-line bg-card px-4 py-3 shadow-lg" style={{ minWidth: 160 }}>
      <Handle type="target" position={Position.Top} />
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
        <div className="font-mono text-sm">{label}</div>
      </div>
      <div className="mt-1 text-xs uppercase tracking-wide text-neutral-500">{health}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
