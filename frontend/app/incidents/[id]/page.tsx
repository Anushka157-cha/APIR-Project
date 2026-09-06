"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ReactFlow, Background, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api";
import { ServiceNode } from "@/components/ServiceNode";

export default function IncidentDetail() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [rollbackMsg, setRollbackMsg] = useState("");

  async function load() {
    const d = await api(`/incidents/${params.id}`);
    setData(d);
  }

  useEffect(() => {
    load().catch((e) => setMsg(String(e)));
  }, [params.id]);

  const inv = data?.incident?.metadata?.investigation;
  const intel = data?.intelligence || data?.incident?.metadata?.intelligence;
  const blast = data?.blast_radius || data?.incident?.metadata?.blast_radius;
  const explain = data?.explain_decision;
  const plan = data?.plans?.[0] || data?.remediation_plans?.[0];
  const rca = inv?.rca;
  const graph = inv?.graph;
  const execution = data?.executions?.[0] || data?.remediation_executions?.[0];

  const nodeTypes = useMemo(() => ({ serviceNode: ServiceNode }), []);

  if (!data) return <p className="text-neutral-500">{msg || "Loading incident…"}</p>;
  const i = data.incident;

  async function investigate() {
    setMsg("Running multi-signal RCA & dependency investigation…");
    try {
      await api(`/incidents/${params.id}/investigate`, { method: "POST" });
      await load();
      setMsg("Investigation completed successfully.");
    } catch (e) {
      setMsg(`Investigation failed: ${e}`);
    }
  }

  async function approve() {
    if (!plan) return;
    setMsg("Executing approved remediation action…");
    try {
      await api(`/remediation/${plan.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ reason: "operator approved via SRE console" }),
      });
      await load();
      setMsg("Remediation executed and verified.");
    } catch (e) {
      setMsg(`Approval failed: ${e}`);
    }
  }

  async function reject() {
    if (!plan) return;
    try {
      await api(`/remediation/${plan.id}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: "operator rejected action" }),
      });
      await load();
    } catch (e) {
      setMsg(`Rejection failed: ${e}`);
    }
  }

  async function triggerRollback() {
    if (!execution) return;
    setRollbackMsg("Initiating safe rollback…");
    try {
      const res = await api(`/remediation/${execution.id}/rollback`, { method: "POST" });
      setRollbackMsg(`Rollback ${res.status}: ${JSON.stringify(res.details || {})}`);
      await load();
    } catch (e) {
      setRollbackMsg(`Rollback failed: ${e}`);
    }
  }

  return (
    <div className="space-y-8">
      {/* Incident Header */}
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-white">{i.title}</h1>
            <span
              className={`rounded px-2.5 py-0.5 font-mono text-xs font-semibold ${
                i.status === "RESOLVED"
                  ? "bg-ok/20 text-ok"
                  : i.status === "FAILED"
                  ? "bg-bad/20 text-bad"
                  : "bg-accent/20 text-accent"
              }`}
            >
              {i.status}
            </span>
          </div>
          <p className="mt-1 text-sm text-neutral-400">{i.description}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs font-mono">
            <span className="rounded border border-line bg-card px-2.5 py-1 text-neutral-300">
              Severity: <strong className={i.severity === "CRITICAL" ? "text-bad" : i.severity === "HIGH" ? "text-warn" : "text-neutral-200"}>{i.severity}</strong>
            </span>
            <span className="rounded border border-line bg-card px-2.5 py-1 text-neutral-300">
              Target: <strong className="text-white">{i.service}</strong>
            </span>
            <span className="rounded border border-line bg-card px-2.5 py-1 text-neutral-300">
              Fingerprint: <strong className="text-accent">{intel?.fingerprint || `${i.service}:${i.incident_type}`}</strong>
            </span>
            {intel?.anomaly_score != null && (
              <span className="rounded border border-line bg-card px-2.5 py-1 text-neutral-300">
                Anomaly Score: <strong className="text-accent">{intel.anomaly_score}</strong>
              </span>
            )}
          </div>
        </div>

        <div className="flex gap-2">
          {i.status !== "RESOLVED" && (
            <button
              onClick={investigate}
              className="rounded bg-accent px-4 py-2 text-xs font-medium text-black transition-opacity hover:opacity-90"
            >
              Run Investigation
            </button>
          )}
          <Link
            href="/incidents/compare"
            className="rounded border border-line bg-card px-3 py-2 text-xs text-neutral-300 hover:border-neutral-500"
          >
            Compare Incident →
          </Link>
        </div>
      </div>

      {msg && <div className="rounded border border-line bg-neutral-900 p-3 text-sm text-accent">{msg}</div>}

      {/* Decision Explainability (FEATURE 12) */}
      <section className="rounded-lg border border-accent/40 bg-card p-5">
        <h2 className="text-base font-semibold text-white">Explain Decision — Root-Cause & Remediation Justification</h2>
        <div className="mt-4 grid gap-4 text-xs md:grid-cols-2">
          <div className="rounded border border-line/60 bg-neutral-900/40 p-3">
            <div className="font-semibold uppercase tracking-wider text-neutral-400">WHAT Happened?</div>
            <div className="mt-1 text-neutral-200">{explain?.what || `Incident on ${i.service} (${i.incident_type})`}</div>
          </div>
          <div className="rounded border border-line/60 bg-neutral-900/40 p-3">
            <div className="font-semibold uppercase tracking-wider text-neutral-400">WHY Was It Detected?</div>
            <div className="mt-1 text-neutral-200">{explain?.why_detected || intel?.explanation || "Multi-signal anomaly exceeded baseline thresholds."}</div>
          </div>
          <div className="rounded border border-line/60 bg-neutral-900/40 p-3">
            <div className="font-semibold uppercase tracking-wider text-neutral-400">WHY Root Cause Selected?</div>
            <div className="mt-1 text-neutral-200">
              {inv?.causal_rca?.causal_narrative || explain?.why_rca || "Corroborated by topology depth, leaf callee precedence, and Prometheus metrics."}
            </div>
          </div>
          <div className="rounded border border-line/60 bg-neutral-900/40 p-3">
            <div className="font-semibold uppercase tracking-wider text-neutral-400">Action Selection & Policy</div>
            <div className="mt-1 text-neutral-200">
              {plan ? `${plan.action_id} on ${plan.target} (${plan.risk} risk, blast radius: ${blast?.blast_radius_level || "LOW"})` : "Evaluation in progress"}
            </div>
          </div>
        </div>
      </section>

      {/* Multi-Signal Anomaly Breakdown (FEATURE 1) */}
      {intel && (
        <section className="rounded-lg border border-line bg-card p-5">
          <h2 className="text-base font-medium text-white">Incident Intelligence & Metric Breakdown</h2>
          <div className="mt-3 grid gap-4 md:grid-cols-4">
            <div className="rounded border border-line/60 bg-neutral-900/40 p-3">
              <div className="text-xs text-neutral-400">Observed Metric Value</div>
              <div className="mt-1 font-mono text-xl text-white">{intel.observed_value}ms</div>
              <div className="text-[11px] text-neutral-500">Baseline: {intel.baseline_value}ms</div>
            </div>
            <div className="rounded border border-line/60 bg-neutral-900/40 p-3">
              <div className="text-xs text-neutral-400">Percentage Deviation</div>
              <div className="mt-1 font-mono text-xl text-warn">+{intel.percentage_deviation}%</div>
              <div className="text-[11px] text-neutral-500">Z-Score: {intel.z_score}</div>
            </div>
            <div className="rounded border border-line/60 bg-neutral-900/40 p-3">
              <div className="text-xs text-neutral-400">Composite Anomaly Score</div>
              <div className="mt-1 font-mono text-xl text-accent">{intel.anomaly_score} / 1.0</div>
              <div className="text-[11px] text-neutral-500">Multi-signal weighted</div>
            </div>
            <div className="rounded border border-line/60 bg-neutral-900/40 p-3">
              <div className="text-xs text-neutral-400">Contributing Signals</div>
              <div className="mt-1 text-[11px] font-mono text-neutral-300">
                {Object.entries(intel.contributors || {}).map(([k, v]: [string, any]) => (
                  <div key={k}>{k.replace(/_/g, " ")}: {v}</div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Blast Radius Analysis (FEATURE 4) */}
      {blast && (
        <section className="rounded-lg border border-line bg-card p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-medium text-white">Operational Blast Radius Analysis</h2>
            <span
              className={`rounded px-2.5 py-0.5 text-xs font-mono font-semibold ${
                blast.blast_radius_level === "HIGH"
                  ? "bg-bad/20 text-bad"
                  : blast.blast_radius_level === "MEDIUM"
                  ? "bg-warn/20 text-warn"
                  : "bg-ok/20 text-ok"
              }`}
            >
              Blast Radius: {blast.blast_radius_level}
            </span>
          </div>
          <div className="mt-3 text-xs text-neutral-300">
            <div>Target: <strong className="font-mono text-white">{blast.target}</strong></div>
            <div className="mt-1">
              Affected Dependency Chain: <span className="font-mono text-accent">{blast.affected_services?.join(" → ")}</span>
            </div>
            <div className="mt-1 text-neutral-400">{blast.description}</div>
          </div>
        </section>
      )}

      {/* Dependency Topology Graph */}
      {graph && (
        <section className="rounded-lg border border-line bg-card p-4">
          <h2 className="mb-3 text-base font-medium text-white">Topology Call Graph & Service States</h2>
          <div className="h-72 rounded border border-line/60 bg-neutral-950">
            <ReactFlow nodes={graph.nodes || []} edges={graph.edges || []} nodeTypes={nodeTypes} fitView>
              <Background />
              <Controls />
            </ReactFlow>
          </div>
        </section>
      )}

      {/* Ranked RCA Hypotheses (FEATURE 2) */}
      <section>
        <h2 className="text-base font-medium text-white">Ranked RCA Hypotheses & Confidence Calibration</h2>
        <ul className="mt-3 space-y-3">
          {rca?.hypotheses?.map((h: any, idx: number) => (
            <li key={idx} className="rounded-lg border border-line bg-card p-4">
              <div className="flex items-center justify-between">
                <strong className="text-sm text-neutral-200">{h.hypothesis}</strong>
                <span className="font-mono text-xs text-accent">Confidence: {Math.round(h.confidence * 100)}%</span>
              </div>
              <p className="mt-1 text-xs text-neutral-400">{rca.summary}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] font-mono text-neutral-400">
                <span className="rounded bg-neutral-800 px-2 py-0.5">Evidence: {h.evidence?.length || 0}</span>
                <span className="rounded bg-neutral-800 px-2 py-0.5">Contradictions: {h.contradicting_evidence?.length || 0}</span>
                {h.score_parts && (
                  <span className="rounded bg-neutral-800 px-2 py-0.5">
                    Breakdown: {Object.entries(h.score_parts).map(([k, v]) => `${k}:${v}`).join(" | ")}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* Recommended Remediation & Policy (FEATURE 3, 10) */}
      {plan && (
        <section className="rounded-lg border border-line bg-card p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-medium text-white">Remediation Policy Decision & Execution</h2>
            <span className="rounded border border-line px-2 py-0.5 font-mono text-xs text-neutral-300">
              Risk: {plan.risk}
            </span>
          </div>
          <div className="mt-3 font-mono text-xs text-accent">
            Action: {plan.action_id} → {plan.target}
          </div>
          <p className="mt-1 text-xs text-neutral-300">{plan.reason}</p>
          <p className="mt-1 text-xs text-neutral-500">Expected Effect: {plan.expected_effect}</p>
          <p className="mt-1 text-xs text-neutral-500">Rollback Counterpart: {plan.rollback_plan}</p>

          <div className="mt-3 text-xs">
            Status: <span className="font-mono font-medium text-white">{plan.status}</span>
            {execution && (
              <span className="ml-3 font-mono text-neutral-400">
                Result: <strong className={execution.result === "ok" ? "text-ok" : "text-bad"}>{execution.result}</strong>
              </span>
            )}
          </div>

          {plan.status === "proposed" && (
            <div className="mt-4 flex gap-3">
              <button
                onClick={approve}
                className="rounded bg-ok px-4 py-1.5 text-xs font-medium text-black hover:opacity-90"
              >
                Approve & Execute
              </button>
              <button
                onClick={reject}
                className="rounded border border-line px-4 py-1.5 text-xs text-neutral-300 hover:border-neutral-500"
              >
                Reject Action
              </button>
            </div>
          )}

          {/* Safe Rollback Option */}
          {execution && (
            <div className="mt-4 border-t border-line/60 pt-3">
              <button
                onClick={triggerRollback}
                className="rounded border border-warn/60 px-3 py-1 text-xs font-mono text-warn hover:bg-warn/10"
              >
                Trigger Rollback ({plan.target})
              </button>
              {rollbackMsg && <span className="ml-3 text-xs text-neutral-400">{rollbackMsg}</span>}
            </div>
          )}
        </section>
      )}

      {/* Real Incident Timeline (FEATURE 6) */}
      <section className="rounded-lg border border-line bg-card p-5">
        <h2 className="text-base font-medium text-white">Verifiable Incident Lifecycle Timeline</h2>
        <ol className="mt-4 space-y-3 font-mono text-xs">
          {data.timeline?.map((e: any, idx: number) => (
            <li key={idx} className="flex items-start gap-4 border-l-2 border-line pl-4">
              <span className="text-neutral-500">{e.created_at?.slice(11, 19) || "T"}</span>
              <span className="font-semibold text-neutral-200">{e.event_type}</span>
              {e.duration_since_prev_seconds != null && e.duration_since_prev_seconds > 0 && (
                <span className="text-[11px] text-accent">+{e.duration_since_prev_seconds.toFixed(1)}s</span>
              )}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
