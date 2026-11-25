"""The model menu and the one access check that gates real (paid) models.

Spec §3.1 and §3.3. Nothing here touches the network or builds a model;
Task 2's ``make_model`` does that from a ``ModelEntry``.
"""
import json
from dataclasses import dataclass
from typing import Literal, Mapping
from urllib.parse import urlsplit

from starlette.requests import Request

from .config import Settings

MODEL_CHOICE_DENIED = "model choice is not available"
UNKNOWN_MODEL = "unknown model"

# Placeholder slug: Task 5's live check confirms it on OpenRouter (and that it
# supports tool calls) before it ships as the default.
DEEPSEEK_SLUG = "deepseek/deepseek-chat"

CREDENTIAL_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
LOOPBACK_BIND = {"127.0.0.1", "::1", "localhost"}
LOOPBACK_CLIENT = {"127.0.0.1", "::1"}
LOOPBACK_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}  # urlsplit strips the brackets
# Any of these means a proxy or tunnel stands between the person and the app.
FORWARDING_HEADERS = ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip")


@dataclass(frozen=True)
class ModelEntry:
    id: str
    label: str
    provider: Literal["anthropic", "openrouter"]
    model: str


# The offline script is not a provider model and is never passed to make_model.
OFFLINE = ModelEntry("offline", "Offline (scripted)", "offline", "")  # type: ignore[arg-type]

DEFAULT_ENTRIES: tuple[ModelEntry, ...] = (
    ModelEntry("claude-haiku", "Claude Haiku 5.5", "anthropic", "claude-haiku-5-5"),
    ModelEntry("deepseek", "DeepSeek (via OpenRouter)", "openrouter", DEEPSEEK_SLUG),
)

_FIELDS = ("id", "label", "provider", "model")


def load_entries(raw: str | None) -> tuple[ModelEntry, ...]:
    """Parse STUDIO_MODELS (a JSON array), or return the defaults when unset."""
    if raw is None or not raw.strip():
        return DEFAULT_ENTRIES
    try:
        items = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"STUDIO_MODELS is not valid JSON: {e}") from None
    if not isinstance(items, list):
        raise ValueError("STUDIO_MODELS must be a JSON array of model entries")
    entries: list[ModelEntry] = []
    seen: set[str] = set()
    for n, item in enumerate(items, 1):
        where = f"STUDIO_MODELS entry {n}"
        if not isinstance(item, dict):
            raise ValueError(f"{where} must be an object with id, label, provider and model")
        for name in _FIELDS:
            if not isinstance(item.get(name), str) or not item[name].strip():
                raise ValueError(f"{where} is missing the field '{name}'")
        if item["id"] == OFFLINE.id:
            raise ValueError(f"{where} uses the reserved id 'offline'")
        if item["id"] in seen:
            raise ValueError(f"{where} repeats the id '{item['id']}'")
        if item["provider"] not in CREDENTIAL_ENV:
            raise ValueError(f"{where} has an unknown provider '{item['provider']}'; use anthropic or openrouter")
        seen.add(item["id"])
        entries.append(ModelEntry(*(item[name] for name in _FIELDS)))
    return tuple(entries)


def credential_set(entry: ModelEntry, env: Mapping[str, str]) -> bool:
    name = CREDENTIAL_ENV.get(entry.provider)
    return bool(name and (env.get(name) or "").strip())


def listed_entries(entries: tuple[ModelEntry, ...], env: Mapping[str, str]) -> tuple[ModelEntry, ...]:
    return (OFFLINE, *(e for e in entries if credential_set(e, env)))


def entry_for(entries: tuple[ModelEntry, ...], model_id: str) -> ModelEntry | None:
    return next((e for e in entries if e.id == model_id), None)


def _host_hostname(host: str | None) -> str | None:
    """The hostname of a Host header (IPv6 brackets and port handled), or None."""
    if not host or any(c in host for c in "@/\\?# "):
        return None
    try:
        return urlsplit("//" + host).hostname
    except ValueError:
        return None


def may_choose_model(request: Request, settings: Settings) -> bool:
    """True only for the person on their own machine. The only gate for real models.

    Every condition must hold: loopback bind, a loopback local socket and peer,
    no forwarding headers, a loopback Host (blocks DNS rebinding), and for POSTs
    an Origin, if sent, that matches Host (blocks cross-site posts).

    The socket address (``scope["server"]``) is the one proxy headers can't
    rewrite. A proxy or tunnel on this machine that adds no forwarding header
    and rewrites Host still passes: no request check can see it, so the README
    says never to run one in front while a key is set. Milestone 4 replaces
    this body with an admin rule.
    """
    if settings.host not in LOOPBACK_BIND:
        return False
    server = request.scope.get("server")
    if not server or server[0] not in LOOPBACK_CLIENT:
        return False
    if request.client is None or request.client.host not in LOOPBACK_CLIENT:
        return False
    if any(name in request.headers for name in FORWARDING_HEADERS):
        return False
    host = request.headers.get("host")
    if _host_hostname(host) not in LOOPBACK_HOSTNAMES:
        return False
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin is not None:
            try:
                parts = urlsplit(origin)
            except ValueError:
                return False
            if parts.scheme not in ("http", "https") or parts.netloc.lower() != host.lower():
                return False
    return True
