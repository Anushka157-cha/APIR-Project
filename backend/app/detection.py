from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependency_graph import SERVICES
from app.prom import PrometheusClient
from app.stats import RollingWindow, ewma, moving_average, zscore

SEVERITY_MAP = {
    "service_crash": "CRITICAL",
    "database_failure": "CRITICAL",
    "error_rate_spike": "HIGH",
    "latency_spike": "HIGH",
    "dependency_failure": "HIGH",
    "resource_anomaly": "MEDIUM",
    "traffic_anomaly": "MEDIUM",
}


class DetectionEngine:
    def __init__(self) -> None:
        self.prom = PrometheusClient()
        self.windows: dict[str, RollingWindow] = defaultdict(lambda: RollingWindow(10))

    async def tick(self, session: AsyncSession) -> list[dict]:
        snap = await self.prom.snapshot()
        created = []
        for service, metrics in snap.items():
            p95 = metrics.get("p95_ms") or 0.0
            err = metrics.get("error_rate") or 0.0
            rps = metrics.get("rps") or 0.0
            health = metrics.get("health")
            self.windows[f"{service}:p95"].add(p95)
            self.windows[f"{service}:err"].add(err)
            self.windows[f"{service}:rps"].add(rps)

            p95_hist = self.windows[f"{service}:p95"].list()
            err_hist = self.windows[f"{service}:err"].list()
            rps_hist = self.windows[f"{service}:rps"].list()

            findings: list[str] = []
            itype = None
            
            if health == 0:
                findings.append("service_crash")
                itype = "service_crash"
            if p95 >= settings.latency_p95_threshold_ms:
                findings.append("latency_threshold")
                itype = itype or "latency_spike"
            if zscore(p95, p95_hist[:-1] or p95_hist) >= settings.zscore_threshold and p95 > 200:
                findings.append("latency_zscore")
                itype = itype or "latency_spike"
            if err >= settings.error_rate_threshold and rps > 0.2:
                findings.append("error_rate_threshold")
                itype = itype or "error_rate_spike"
            if zscore(rps, rps_hist[:-1] or rps_hist) >= settings.traffic_zscore_threshold and rps > 1:
                findings.append("traffic_zscore")
                itype = itype or "traffic_anomaly"
            ewma_p95 = ewma(p95_hist, 0.35)
            if ewma_p95 >= settings.latency_p95_threshold_ms * 0.9 and p95 >= settings.latency_p95_threshold_ms:
                findings.append("latency_ewma")
                itype = itype or "latency_spike"
            ma_err = moving_average(err_hist, 5)
            if ma_err >= settings.error_rate_threshold:
                findings.append("error_moving_average")
                itype = itype or "error_rate_spike"

            db_lat_series = await self.prom.query(
                f'histogram_quantile(0.95, sum by (le) (rate(database_latency_seconds_bucket{{service="{service}"}}[1m]))) * 1000'
            )
            db_p95 = 0.0
            if db_lat_series:
                try:
                    db_p95 = float(db_lat_series[0]["value"][1])
                except Exception:
                    db_p95 = 0.0
            if db_p95 >= 1000:
                findings.append("database_latency")
                itype = "database_failure"

            # Log diagnostic info for payment-service after detection decisions
            if service == "payment-service":
                import logging
                logger = logging.getLogger("apir.detection")
                zscore_val = zscore(p95, p95_hist[:-1] or p95_hist)
                ewma_val = ewma(p95_hist, 0.35)
                logger.info(f"payment-service cycle: p95={p95:.2f}ms (threshold={settings.latency_p95_threshold_ms}), zscore={zscore_val:.2f} (threshold={settings.zscore_threshold}), ewma={ewma_val:.2f}, window_size={len(p95_hist)}, findings={findings}, itype={itype}")

            if not itype:
                continue
            open_existing = await session.execute(
                text(
                    """
                    SELECT incident_id FROM incidents
                    WHERE service=:svc AND status NOT IN ('RESOLVED','FAILED')
                      AND incident_type=:itype
                      AND detected_at > NOW() - INTERVAL '2 minutes'
                    """
                ),
                {"svc": service, "itype": itype},
            )
            existing_incident = open_existing.first()
            if existing_incident:
                import logging
                logging.getLogger("apir.detection").info(f"Suppressed duplicate incident for {service} ({itype}) due to active incident {existing_incident[0]}")
                continue
            incident = await self._create(
                session,
                service=service,
                itype=itype,
                findings=findings,
                metrics=metrics,
            )
            created.append(incident)
        return created

    async def _create(self, session: AsyncSession, service: str, itype: str, findings: list[str], metrics: dict) -> dict:
        iid = str(uuid.uuid4())
        severity = SEVERITY_MAP.get(itype, "MEDIUM")
        title = f"{itype.replace('_', ' ')} on {service}"
        description = f"Detector findings: {', '.join(findings)}"
        baseline = await self.prom.baseline(service)
        
        from app.incident_intelligence import build_intelligence_record
        intel = build_intelligence_record(service, itype, metrics, findings, baseline)
        
        meta = {
            "findings": findings,
            "metrics": metrics,
            "metric_history": baseline,
            "baseline_source": "prometheus_range",
            "intelligence": intel,
            "fingerprint": intel["fingerprint"],
            "anomaly_score": intel["anomaly_score"],
            "contributors": intel["contributors"],
        }
        await session.execute(
            text(
                """
                INSERT INTO incidents (incident_id, title, description, severity, status, service, incident_type, metadata)
                VALUES (:id, :title, :desc, :sev, 'OPEN', :svc, :itype, :meta)
                """
            ),
            {
                "id": iid,
                "title": title,
                "desc": description,
                "sev": severity,
                "svc": service,
                "itype": itype,
                "meta": json.dumps(meta),
            },
        )
        await session.execute(
            text(
                "INSERT INTO incident_events (incident_id, event_type, payload) VALUES (:id, 'INCIDENT_DETECTED', :p)"
            ),
            {"id": iid, "p": json.dumps({"findings": findings, "anomaly_score": intel["anomaly_score"], "contributors": intel["contributors"], "fingerprint": intel["fingerprint"]})},
        )
        await session.commit()
        return {
            "incident_id": iid,
            "title": title,
            "severity": severity,
            "status": "OPEN",
            "service": service,
            "incident_type": itype,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "fingerprint": intel["fingerprint"],
            "anomaly_score": intel["anomaly_score"],
        }
