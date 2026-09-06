"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function CompareIncidentsPage() {
  const [incidents, setIncidents] = useState<any[]>([]);
  const [idA, setIdA] = useState("");
  const [idB, setIdB] = useState("");
  const [comparison, setComparison] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/incidents")
      .then((data) => {
        setIncidents(data || []);
        if (data && data.length >= 2) {
          setIdA(data[0].incident_id);
          setIdB(data[1].incident_id);
        } else if (data && data.length === 1) {
          setIdA(data[0].incident_id);
        }
      })
      .catch((e) => setError(String(e)));
  }, []);

  async function handleCompare() {
    if (!idA || !idB || idA === idB) {
      setError("Please select two distinct incidents to compare.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await api(`/incidents/compare?a=${idA}&b=${idB}`);
      setComparison(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (idA && idB && idA !== idB) {
      handleCompare();
    }
  }, [idA, idB]);

  const a = comparison?.incident_a;
  const b = comparison?.incident_b;
  const comp = comparison?.comparison;

  const compareRows = [
    { label: "Incident ID", valA: a?.incident_id?.slice(0, 8), valB: b?.incident_id?.slice(0, 8) },
    { label: "Affected Service", valA: a?.service, valB: b?.service, highlight: a?.service === b?.service },
    { label: "Incident Type", valA: a?.incident_type, valB: b?.incident_type, highlight: a?.incident_type === b?.incident_type },
    { label: "Severity", valA: a?.severity, valB: b?.severity },
    { label: "Status", valA: a?.status, valB: b?.status },
    { label: "Anomaly Score", valA: a?.anomaly_score != null ? `${a.anomaly_score}` : "N/A", valB: b?.anomaly_score != null ? `${b.anomaly_score}` : "N/A" },
    { label: "RCA Confidence", valA: a?.rca_confidence != null ? `${Math.round(a.rca_confidence * 100)}%` : "N/A", valB: b?.rca_confidence != null ? `${Math.round(b.rca_confidence * 100)}%` : "N/A" },
    { label: "Root Cause", valA: a?.root_cause || "N/A", valB: b?.root_cause || "N/A" },
    { label: "Blast Radius", valA: a?.blast_radius || "LOW", valB: b?.blast_radius || "LOW" },
    { label: "Resolution Time", valA: a?.resolution_time_seconds != null ? `${a.resolution_time_seconds.toFixed(1)}s` : "Pending", valB: b?.resolution_time_seconds != null ? `${b.resolution_time_seconds.toFixed(1)}s` : "Pending" },
    { label: "Fingerprint", valA: a?.fingerprint || "N/A", valB: b?.fingerprint || "N/A", highlight: comp?.is_recurrence },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Incident Comparison & Failure Recurrence Analysis</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Compare multi-signal anomalies, causal RCA decisions, remediation actions, and MTTR across incidents.
        </p>
      </div>

      {/* Selectors */}
      <div className="grid gap-4 rounded-lg border border-line bg-card p-5 md:grid-cols-2">
        <div>
          <label className="text-xs uppercase tracking-wider text-neutral-400">Incident A</label>
          <select
            value={idA}
            onChange={(e) => setIdA(e.target.value)}
            className="mt-2 w-full rounded border border-line bg-neutral-900 px-3 py-2 text-sm text-white"
          >
            <option value="">Select Incident A</option>
            {incidents.map((inc) => (
              <option key={inc.incident_id} value={inc.incident_id}>
                {inc.incident_id.slice(0, 8)} — {inc.service} ({inc.status})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs uppercase tracking-wider text-neutral-400">Incident B</label>
          <select
            value={idB}
            onChange={(e) => setIdB(e.target.value)}
            className="mt-2 w-full rounded border border-line bg-neutral-900 px-3 py-2 text-sm text-white"
          >
            <option value="">Select Incident B</option>
            {incidents.map((inc) => (
              <option key={inc.incident_id} value={inc.incident_id}>
                {inc.incident_id.slice(0, 8)} — {inc.service} ({inc.status})
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && <p className="text-sm text-bad">{error}</p>}
      {loading && <p className="text-sm text-neutral-400">Analyzing incidents…</p>}

      {/* Recurrence Banner */}
      {comp && comp.is_recurrence && (
        <div className="rounded-lg border border-warn/40 bg-warn/10 p-4 text-warn">
          <div className="font-medium">⚠️ Recurring Incident Pattern Detected</div>
          <p className="mt-1 text-xs text-neutral-300">
            Both incidents share the exact deterministic fingerprint ({a?.fingerprint}), indicating an operational recurrence
            on service <span className="font-mono text-white">{a?.service}</span>.
          </p>
        </div>
      )}

      {/* Side-by-Side Comparison Table */}
      {comparison && (
        <div className="overflow-hidden rounded-lg border border-line bg-card">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-neutral-900/60 text-xs uppercase text-neutral-400">
              <tr>
                <th className="py-3 px-5 w-1/4">Attribute</th>
                <th className="py-3 px-5 w-3/8 text-accent">Incident A</th>
                <th className="py-3 px-5 w-3/8 text-accent">Incident B</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/60 font-mono text-xs">
              {compareRows.map((row) => (
                <tr
                  key={row.label}
                  className={`transition-colors hover:bg-neutral-800/30 ${
                    row.highlight ? "bg-accent/5 font-semibold" : ""
                  }`}
                >
                  <td className="py-3 px-5 font-sans text-xs text-neutral-400">{row.label}</td>
                  <td className="py-3 px-5 text-neutral-200">{row.valA}</td>
                  <td className="py-3 px-5 text-neutral-200">{row.valB}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
