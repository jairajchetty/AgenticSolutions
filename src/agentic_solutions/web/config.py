"""Web app settings, read once from the environment (spec §10).

Only the settings milestone 1 needs live here; Live mode, budgets and the
proxy settings arrive in later milestones.
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

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            checkpoint_db=env.get("CHECKPOINT_DB", cls.checkpoint_db),
            worker_threads=int(env.get("WORKER_THREADS", cls.worker_threads)),
            session_secret=env.get("SESSION_SECRET") or secrets.token_hex(32),
            offline_latency_scale=float(env.get("OFFLINE_LATENCY_SCALE", cls.offline_latency_scale)),
            max_input_chars=int(env.get("MAX_INPUT_CHARS", cls.max_input_chars)),
        )
