from __future__ import annotations

import asyncio
from app.action_registry import validate_action
from app.config import settings
from app.failures import stop_all_for_target


async def execute_action(action_id: str, target: str, extra: dict | None = None) -> dict:
    spec = validate_action(action_id, target)
    extra = extra or {}
    details = {"action": action_id, "target": target, "docker": None}
    
    # Dry-run mode: simulate without executing
    if settings.dry_run_mode:
        details["dry_run"] = True
        details["simulation"] = f"Would execute {action_id} on {target}"
        return {"ok": True, "spec": spec, "details": details, "dry_run": True}

    if action_id in {"restart_service", "rollback_service"}:
        # Map both naming conventions for failure clearing
        failure_targets = [target]
        if target.endswith("-service"):
            failure_targets.append(target.replace("-service", ""))
        else:
            failure_targets.append(f"{target}-service")
        
        for ft in failure_targets:
            try:
                await stop_all_for_target(ft)
            except Exception:
                pass
        details["cleared_failure_flags"] = True
        
        # Execute with timeout
        try:
            details["docker"] = await asyncio.wait_for(
                asyncio.to_thread(_docker_restart, target),
                timeout=settings.remediation_timeout_seconds
            )
        except asyncio.TimeoutError:
            details["docker"] = {"ok": False, "error": f"remediation timeout after {settings.remediation_timeout_seconds}s"}
        
        if not details["docker"]["ok"]:
            return {"ok": False, "spec": spec, "details": details, "error": details["docker"]["error"]}

    if action_id == "scale_service":
        replicas = int(extra.get("replicas") or 2)
        if replicas < 1 or replicas > 3:
            raise ValueError("replicas must be 1-3")
        details["replicas"] = replicas
        details["note"] = "Scale recorded; compose replica changes require docker socket"

    if action_id == "enable_feature_flag":
        flag = extra.get("flag") or "safe_mode"
        import redis.asyncio as redis

        r = redis.from_url(settings.redis_url, decode_responses=True)
        await r.set(f"flag:{target}:{flag}", "1")
        await r.aclose()
        details["flag"] = flag

    return {"ok": True, "spec": spec, "details": details}


async def rollback_action(execution_id: str, target: str) -> dict:
    """Rollback a remediation action if enabled."""
    if not settings.enable_rollback:
        return {"ok": False, "error": "rollback is disabled"}
    
    details = {"action": "rollback", "target": target, "dry_run": settings.dry_run_mode}
    
    if settings.dry_run_mode:
        details["simulation"] = f"Would rollback {target}"
        return {"ok": True, "details": details, "dry_run": True}
    
    # Clear any failure flags that might have been set
    failure_targets = [target]
    if target.endswith("-service"):
        failure_targets.append(target.replace("-service", ""))
    else:
        failure_targets.append(f"{target}-service")
    
    for ft in failure_targets:
        try:
            await stop_all_for_target(ft)
        except Exception:
            pass
    
    details["cleared_failure_flags"] = True
    return {"ok": True, "details": details}


def _docker_restart(target: str) -> dict:
    """Restart by Compose labels, avoiding fragile generated container names."""
    try:
        import docker

        client = docker.from_env()
        # Map service names to compose service names (remove -service suffix)
        compose_target = target.replace("-service", "")
        containers = client.containers.list(
            all=True,
            filters={"label": [f"com.docker.compose.service={compose_target}"]},
        )
        if not containers:
            return {"ok": False, "error": f"no Compose container found for {target} (tried {compose_target})"}
        container = containers[0]
        container.restart(timeout=10)
        container.reload()
        if container.status != "running":
            return {"ok": False, "error": f"container {container.name} is {container.status} after restart"}
        return {"ok": True, "container": container.name, "status": container.status}
    except Exception as exc:
        return {"ok": False, "error": f"docker restart failed: {type(exc).__name__}: {exc}"}
