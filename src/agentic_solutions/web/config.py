"""Web app settings, read once from the environment (spec §10).

Only the settings milestone 1 and the approval demo need live here; Live
mode, budgets and the proxy settings arrive in later milestones.
"""
import os
import secrets
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    checkpoint_db: str = "./data/checkpoints.sqlite"
    worker_threads: int = 128
    # A random secret per start is fine for development: restarting just
    # invalidates the cookies. Production must set SESSION_SECRET.
    session_secret: str = field(default_factory=lambda: secrets.token_hex(32))
    offline_latency_scale: float = 1.0  # builder setting: 0 disables scripted delays
    max_input_chars: int = 2000  # longest message a run accepts (422 above it)
    # The approval demo's ERP (Approval spec §6, plan ruling 3). With no URL the
    # app runs the ERP server in-process; with one it connects over HTTP and
    # needs the secret that server was started with.
    erp_mcp_url: str | None = None
    erp_approval_secret: str | None = None  # None (in-process only): random per start
    erp_auto_approve_limit_zar: float = 5000
    erp_db: str = "./data/erp.sqlite"
    erp_tenant_ttl_hours: float = 168

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            checkpoint_db=env.get("CHECKPOINT_DB", cls.checkpoint_db),
            worker_threads=int(env.get("WORKER_THREADS", cls.worker_threads)),
            session_secret=env.get("SESSION_SECRET") or secrets.token_hex(32),
            offline_latency_scale=float(env.get("OFFLINE_LATENCY_SCALE", cls.offline_latency_scale)),
            max_input_chars=int(env.get("MAX_INPUT_CHARS", cls.max_input_chars)),
            erp_mcp_url=env.get("ERP_MCP_URL") or None,
            erp_approval_secret=env.get("ERP_APPROVAL_SECRET") or None,
            erp_auto_approve_limit_zar=float(
                env.get("ERP_AUTO_APPROVE_LIMIT_ZAR") or cls.erp_auto_approve_limit_zar),
            erp_db=env.get("ERP_DB") or cls.erp_db,
            erp_tenant_ttl_hours=float(env.get("ERP_TENANT_TTL_HOURS") or cls.erp_tenant_ttl_hours),
        )
