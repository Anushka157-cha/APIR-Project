"use client";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";

export default function EvaluationPage() {
  const [data, setData] = useState<any>(null); const [error, setError] = useState("");
  useEffect(() => { api("/evaluation").then(setData).catch((e) => setError(String(e))); }, []);
  if (error) return <p className="text-bad">{error}</p>;
  if (!data) return <p className="text-neutral-500">Loading evaluation…</p>;
  const s = data.summary || {};
  const quality = [{ name: "Detection", value: (s.detection_accuracy || 0) * 100 }, { name: "RCA", value: (s.rca_accuracy || 0) * 100 }, { name: "Remediation", value: (s.remediation_success_rate || 0) * 100 }, { name: "False positive", value: (s.false_positive_rate || 0) * 100 }];
  const timing = ["mttd_ms", "mtti_ms", "mttr_ms"].map((name) => ({ name: name.replace("_ms", "").toUpperCase(), value: s[name] || 0 }));
  return <div><h1 className="text-2xl font-semibold">Evaluation</h1><p className="mt-1 text-sm text-neutral-400">Derived only from recorded replay runs.</p><div className="mt-6 grid gap-4 md:grid-cols-2"><Chart title="Quality rates (%)" data={quality} max={100}/><Chart title="Timing (ms)" data={timing}/></div><h2 className="mt-8 text-lg font-medium">Recorded replays</h2><table className="mt-3 w-full text-left text-sm"><thead className="text-neutral-500"><tr><th>Scenario</th><th>Detected</th><th>RCA</th><th>Remediation</th><th>MTTR</th></tr></thead><tbody>{(data.runs || []).map((r:any)=><tr className="border-t border-line" key={r.id}><td className="py-2 font-mono">{r.scenario}</td><td>{r.incident_id ? "yes" : "no"}</td><td>{String(r.rca_correct)}</td><td>{String(r.remediation_success)}</td><td>{r.resolution_ms ?? "—"}</td></tr>)}</tbody></table></div>;
}
function Chart({ title, data, max }: { title: string; data: any[]; max?: number }) { return <section className="h-72 rounded border border-line bg-card p-4"><h2 className="font-medium">{title}</h2><ResponsiveContainer width="100%" height="90%"><BarChart data={data}><CartesianGrid stroke="#25324b"/><XAxis dataKey="name"/><YAxis domain={max ? [0, max] : [0, "auto"]}/><Tooltip/><Bar dataKey="value" fill="#4fd1c5"/></BarChart></ResponsiveContainer></section>; }
