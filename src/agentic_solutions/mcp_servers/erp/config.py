"""ERP server settings, read from the environment (Approval spec §6, §9.3)."""

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ErpSettings:
    db: str = "./data/erp.sqlite"
    # Random per start unless ERP_APPROVAL_SECRET is set. A separate server
    # process and the Studio must share it, so whoever starts them over HTTP
    # has to set it (plan ruling 3).
    secret: bytes = b""
    auto_limit_zar: float = 5000.0
    tenant_ttl_hours: float = 168.0
    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ErpSettings":
        env = os.environ if env is None else env
        secret = env.get("ERP_APPROVAL_SECRET")
        return cls(
            db=env.get("ERP_DB") or cls.db,
            secret=secret.encode("utf-8") if secret else secrets.token_bytes(32),
            auto_limit_zar=float(env.get("ERP_AUTO_APPROVE_LIMIT_ZAR") or cls.auto_limit_zar),
            tenant_ttl_hours=float(env.get("ERP_TENANT_TTL_HOURS") or cls.tenant_ttl_hours),
            host=env.get("ERP_HOST") or cls.host,
            port=int(env.get("ERP_PORT") or cls.port),
        )
