"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
export default function ServicesPage() {
  const [services, setServices] = useState<any[]>([]); const [selected, setSelected] = useState<any>(null); const [error, setError] = useState("");
  useEffect(() => { api("/services").then(setServices).catch(e => setError(String(e))); }, []);
  if (error) return <p className="text-bad">{error}</p>;
  return <div><h1 className="text-2xl font-semibold">Services</h1><p className="mt-1 text-sm text-neutral-400">Live Prometheus telemetry.</p><table className="mt-6 w-full text-left text-sm"><thead className="text-neutral-500"><tr><th>Service</th><th>Health</th><th>p95</th><th>p99</th><th>Error rate</th><th>RPS</th><th>Active</th></tr></thead><tbody>{services.map(s => <tr onClick={() => api(`/services/${s.name}/dependencies`).then(setSelected)} className="cursor-pointer border-t border-line hover:bg-card" key={s.name}><td className="py-3 font-mono">{s.name}</td><td>{s.health ? "healthy" : "unknown"}</td><td>{s.p95_ms?.toFixed?.(1) ?? "—"}</td><td>{s.p99_ms?.toFixed?.(1) ?? "—"}</td><td>{s.error_rate?.toFixed?.(3) ?? "—"}</td><td>{s.rps?.toFixed?.(2) ?? "—"}</td><td>{s.active ?? "—"}</td></tr>)}</tbody></table>{selected && <section className="mt-6 rounded border border-line bg-card p-4"><h2 className="font-medium">{selected.service} dependencies</h2><p className="mt-2 text-sm text-neutral-400">Upstream: {selected.upstream?.join(", ") || "none"}</p><p className="text-sm text-neutral-400">Downstream: {selected.downstream?.join(", ") || "none"}</p></section>}</div>;
}
