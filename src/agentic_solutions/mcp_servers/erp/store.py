"""The mock ERP's system of record: SQLite, one file, every row scoped to a tenant.

`submit_purchase_order` is where the guarantee lives. It refuses (and audits
the refusal) unless the approval token is signed with the shared secret and
bound to this exact tenant, requisition, version and content hash, and the
quotes and the budget still hold (Approval spec §4.2).

Money is whole rands throughout: list prices are ints, discounts go through
Decimal, and every amount is rounded to an int before it is stored.
"""

import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from importlib import resources
from pathlib import Path

from agentic_solutions.common.approval_tokens import TokenError, verify

from .policy import format_zar

QUOTE_TTL_S = 30 * 60
MAX_RESULTS = 10
MAX_QUANTITY = 999
MAX_LINES = 20
MAX_TEXT = 1000
REQUESTED_BY = "agent"
STUDIO_EVENTS = ("approval_requested", "approved", "rejected", "auto_approved")

MISMATCH = "The approval does not match this request (it was changed after approval)."
TOKEN_EXPIRED = "The approval has expired."
QUOTE_EXPIRED = "A price quote has expired. Ask for a new quote."
ALREADY_ORDERED = "This request was already ordered."
INVALID = "Invalid approval."

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant TEXT PRIMARY KEY,
    last_seen REAL NOT NULL,
    quote_seq INTEGER NOT NULL DEFAULT 0,
    req_seq INTEGER NOT NULL DEFAULT 0,
    po_seq INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS budgets (
    tenant TEXT NOT NULL,
    cost_centre TEXT NOT NULL,
    allocated INTEGER NOT NULL,
    committed INTEGER NOT NULL,
    PRIMARY KEY (tenant, cost_centre)
);
CREATE TABLE IF NOT EXISTS quotes (
    tenant TEXT NOT NULL,
    quote_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    line_total INTEGER NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY (tenant, quote_id)
);
CREATE TABLE IF NOT EXISTS requisitions (
    tenant TEXT NOT NULL,
    req_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    cost_centre TEXT NOT NULL,
    justification TEXT NOT NULL,
    lines TEXT NOT NULL,
    total INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    po_number TEXT,
    idempotency_key TEXT,
    PRIMARY KEY (tenant, req_id)
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant TEXT NOT NULL,
    req_id TEXT NOT NULL,
    ts REAL NOT NULL,
    event TEXT NOT NULL,
    version INTEGER NOT NULL,
    actor TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_by_req ON audit (tenant, req_id, seq);
"""

TENANT_TABLES = ("budgets", "quotes", "requisitions", "audit", "tenants")


class ErpError(Exception):
    """A plain, person-readable failure. `code` is not_found, invalid, refused or expired."""

    CODES = ("not_found", "invalid", "refused", "expired")

    def __init__(self, code: str, message: str):
        if code not in self.CODES:
            raise ValueError(f"unknown ErpError code: {code}")
        super().__init__(message)
        self.code = code


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def _discount(quantity: int) -> Decimal:
    if quantity >= 50:
        return Decimal("0.10")
    if quantity >= 10:
        return Decimal("0.05")
    return Decimal(0)


def _content_hash(req_id, version, cost_centre, justification, lines, total) -> str:
    body = {
        "req_id": req_id,
        "version": version,
        "cost_centre": cost_centre,
        "justification": justification,
        "lines": [
            {k: line[k] for k in ("sku", "quantity", "unit_price_zar", "quote_id")} for line in lines
        ],
        "total_zar": total,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_fixtures() -> dict:
    text = resources.files(__package__).joinpath("fixtures.json").read_text(encoding="utf-8")
    return json.loads(text)


class ErpStore:
    def __init__(
        self,
        path: str,
        *,
        secret: bytes,
        auto_limit_zar: float,
        tenant_ttl_hours: float,
        clock: Callable[[], float] = time.time,
    ):
        if not secret:
            raise ValueError("the ERP needs a non-empty approval secret")
        self._secret = secret
        self._limit = auto_limit_zar
        self._ttl_s = tenant_ttl_hours * 3600
        self._clock = clock
        self._lock = threading.Lock()
        fixtures = _load_fixtures()
        self._items = {i["sku"]: i for i in fixtures["catalogue"]}
        self._suppliers = {s["supplier_id"]: s for s in fixtures["suppliers"]}
        self._cost_centres = {c["cost_centre"]: c for c in fixtures["cost_centres"]}
        if path != ":memory:" and not path.startswith("file:"):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------ plumbing

    def _run(self, tenant, fn):
        """Run fn(db) for one tenant in one transaction, under the lock.

        A refusal is committed (its audit row must persist) and re-raised;
        anything else that fails rolls back.
        """
        if not isinstance(tenant, str) or not tenant.strip() or len(tenant) > 200:
            raise ErpError("invalid", "A tenant is required.")
        with self._lock:
            if self._conn is None:
                raise RuntimeError("the ERP store is closed")
            db = self._conn
            try:
                self._purge_and_touch(db, tenant)
                result = fn(db)
                db.commit()
                return result
            except ErpError as err:
                if err.code == "refused":
                    db.commit()
                else:
                    db.rollback()
                raise
            except BaseException:
                db.rollback()
                raise

    def _purge_and_touch(self, db, tenant):
        now = self._clock()
        stale = [r[0] for r in db.execute(
            "SELECT tenant FROM tenants WHERE last_seen < ?", (now - self._ttl_s,))]
        for old in stale:
            for table in TENANT_TABLES:
                db.execute(f"DELETE FROM {table} WHERE tenant = ?", (old,))
        if db.execute("UPDATE tenants SET last_seen = ? WHERE tenant = ?", (now, tenant)).rowcount:
            return
        db.execute("INSERT INTO tenants (tenant, last_seen) VALUES (?, ?)", (tenant, now))
        db.executemany(
            "INSERT INTO budgets (tenant, cost_centre, allocated, committed) VALUES (?, ?, ?, ?)",
            [(tenant, c["cost_centre"], c["allocated"], c["committed"])
             for c in self._cost_centres.values()],
        )

    def _next(self, db, tenant, counter):
        db.execute(f"UPDATE tenants SET {counter} = {counter} + 1 WHERE tenant = ?", (tenant,))
        return db.execute(f"SELECT {counter} FROM tenants WHERE tenant = ?", (tenant,)).fetchone()[0]

    def _audit(self, db, tenant, req_id, event, version, actor, detail=""):
        db.execute(
            "INSERT INTO audit (tenant, req_id, ts, event, version, actor, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant, req_id, self._clock(), event, version, actor, detail or ""),
        )

    def _cost_centre(self, cost_centre):
        key = cost_centre.strip().upper() if isinstance(cost_centre, str) else ""
        if key not in self._cost_centres:
            known = ", ".join(self._cost_centres)
            raise ErpError("not_found", f"There is no cost centre {cost_centre!r}. Known: {known}.")
        return key

    def _budget(self, db, tenant, cost_centre):
        row = db.execute(
            "SELECT allocated, committed FROM budgets WHERE tenant = ? AND cost_centre = ?",
            (tenant, cost_centre),
        ).fetchone()
        return {
            "cost_centre": cost_centre,
            "name": self._cost_centres[cost_centre]["name"],
            "allocated": row["allocated"],
            "committed": row["committed"],
            "remaining": row["allocated"] - row["committed"],
        }

    def _req_row(self, db, tenant, req_id):
        row = None
        if isinstance(req_id, str):
            row = db.execute(
                "SELECT * FROM requisitions WHERE tenant = ? AND req_id = ?", (tenant, req_id)
            ).fetchone()
        if row is None:
            raise ErpError("not_found", f"There is no requisition {req_id!r}.")
        return row

    @staticmethod
    def _req_dict(row):
        out = {
            "req_id": row["req_id"],
            "version": row["version"],
            "cost_centre": row["cost_centre"],
            "justification": row["justification"],
            "lines": json.loads(row["lines"]),
            "total_zar": row["total"],
            "content_hash": row["content_hash"],
            "status": row["status"],
        }
        if row["po_number"]:
            out["po_number"] = row["po_number"]
        return out

    def _lines_from_quotes(self, db, tenant, lines):
        if not isinstance(lines, list) or not lines:
            raise ErpError("invalid", "A requisition needs at least one line with a quote_id.")
        if len(lines) > MAX_LINES:
            raise ErpError("invalid", f"A requisition can have at most {MAX_LINES} lines.")
        now = self._clock()
        out, seen_quotes, seen_skus = [], set(), set()
        for line in lines:
            quote_id = line.get("quote_id") if isinstance(line, dict) else None
            if not isinstance(quote_id, str) or not quote_id:
                raise ErpError("invalid", "Each line needs a quote_id from get_price_quote.")
            if quote_id in seen_quotes:
                raise ErpError("invalid", f"Quote {quote_id} is used twice.")
            seen_quotes.add(quote_id)
            q = db.execute(
                "SELECT * FROM quotes WHERE tenant = ? AND quote_id = ?", (tenant, quote_id)
            ).fetchone()
            if q is None:
                raise ErpError("not_found", f"There is no price quote {quote_id!r}.")
            if now >= q["expires_at"]:
                raise ErpError("expired", QUOTE_EXPIRED)
            item = self._items.get(q["sku"])
            if item is None:
                raise ErpError("not_found", f"There is no catalogue item {q['sku']!r}.")
            if q["sku"] in seen_skus:
                raise ErpError(
                    "invalid", f"{q['sku']} appears twice. Ask for one quote with the full quantity.")
            seen_skus.add(q["sku"])
            out.append({
                "sku": q["sku"],
                "name": item["name"],
                "quantity": q["quantity"],
                "unit_price_zar": q["unit_price"],
                "line_total_zar": q["line_total"],
                "quote_id": quote_id,
                "quote_expires_at": _iso(q["expires_at"]),
                "quote_expires_at_ts": q["expires_at"],
            })
        return out

    @staticmethod
    def _text(value, what):
        if not isinstance(value, str) or not value.strip():
            raise ErpError("invalid", f"Give a short {what}.")
        if len(value) > MAX_TEXT:
            raise ErpError("invalid", f"The {what} is too long (at most {MAX_TEXT} characters).")
        return value.strip()

    # ------------------------------------------------------------ read tools

    def search_catalogue(self, tenant, query, category=None, max_unit_price=None):
        words = [w[:-1] if len(w) > 3 and w.endswith("s") else w
                 for w in str(query or "").lower().split()]
        cat = category.strip().lower() if isinstance(category, str) and category.strip() else None
        if max_unit_price is not None and not isinstance(max_unit_price, (int, float)):
            raise ErpError("invalid", "max_unit_price must be a number of rands.")

        def find(_db):
            hits = []
            for item in self._items.values():
                hay = f"{item['sku']} {item['name']} {item['category']}".lower()
                if not all(w in hay for w in words):
                    continue
                if cat is not None and item["category"] != cat:
                    continue
                if max_unit_price is not None and item["unit_price_zar"] > max_unit_price:
                    continue
                hits.append({k: item[k] for k in
                             ("sku", "name", "unit_price_zar", "supplier_id", "category")})
            return hits[:MAX_RESULTS]

        return self._run(tenant, find)

    def get_supplier(self, tenant, supplier_id):
        def find(_db):
            supplier = self._suppliers.get(supplier_id) if isinstance(supplier_id, str) else None
            if supplier is None:
                raise ErpError("not_found", f"There is no supplier {supplier_id!r}.")
            return dict(supplier)

        return self._run(tenant, find)

    def check_budget(self, tenant, cost_centre):
        return self._run(tenant, lambda db: self._budget(db, tenant, self._cost_centre(cost_centre)))

    def get_price_quote(self, tenant, sku, quantity):
        def quote(db):
            item = self._items.get(sku) if isinstance(sku, str) else None
            if item is None:
                raise ErpError("not_found", f"There is no catalogue item {sku!r}.")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or not (
                    1 <= quantity <= MAX_QUANTITY):
                raise ErpError("invalid", f"Quantity must be a whole number from 1 to {MAX_QUANTITY}.")
            discount = _discount(quantity)
            unit = int((Decimal(item["unit_price_zar"]) * (1 - discount))
                       .quantize(Decimal(1), rounding=ROUND_HALF_UP))
            total = unit * quantity
            now = self._clock()
            expires = now + QUOTE_TTL_S
            quote_id = f"Q-{self._next(db, tenant, 'quote_seq'):04d}"
            db.execute(
                "INSERT INTO quotes (tenant, quote_id, sku, quantity, unit_price, line_total,"
                " issued_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (tenant, quote_id, sku, quantity, unit, total, now, expires),
            )
            return {
                "quote_id": quote_id,
                "sku": sku,
                "name": item["name"],
                "quantity": quantity,
                "list_price_zar": item["unit_price_zar"],
                "discount_pct": int(discount * 100),
                "unit_price_zar": unit,
                "line_total_zar": total,
                "expires_at": _iso(expires),
                "expires_at_ts": expires,
            }

        return self._run(tenant, quote)

    def get_requisition(self, tenant, req_id):
        return self._run(tenant, lambda db: self._req_dict(self._req_row(db, tenant, req_id)))

    def get_audit_trail(self, tenant, req_id):
        def trail(db):
            self._req_row(db, tenant, req_id)
            rows = db.execute(
                "SELECT ts, event, version, actor, detail FROM audit"
                " WHERE tenant = ? AND req_id = ? ORDER BY seq",
                (tenant, req_id),
            )
            return [{"ts": _iso(r["ts"]), "event": r["event"], "version": r["version"],
                     "actor": r["actor"], "detail": r["detail"]} for r in rows]

        return self._run(tenant, trail)

    # ------------------------------------------------------------ drafting

    def create_requisition(self, tenant, cost_centre, lines, justification):
        def create(db):
            cc = self._cost_centre(cost_centre)
            text = self._text(justification, "justification")
            built = self._lines_from_quotes(db, tenant, lines)
            req_id = f"REQ-{self._next(db, tenant, 'req_seq'):04d}"
            self._write_version(db, tenant, req_id, 1, cc, text, built, insert=True)
            self._audit(db, tenant, req_id, "created", 1, REQUESTED_BY,
                        f"{len(built)} line(s), {format_zar(sum(x['line_total_zar'] for x in built))}"
                        f" for {cc}")
            return self._req_dict(self._req_row(db, tenant, req_id))

        return self._run(tenant, create)

    def update_requisition(self, tenant, req_id, lines=None, justification=None):
        def update(db):
            row = self._req_row(db, tenant, req_id)
            if row["status"] != "draft":
                raise ErpError("invalid", ALREADY_ORDERED)
            if lines is None and justification is None:
                raise ErpError("invalid", "Nothing to change: give new lines or a new justification.")
            built = (self._lines_from_quotes(db, tenant, lines) if lines is not None
                     else json.loads(row["lines"]))
            text = (self._text(justification, "justification") if justification is not None
                    else row["justification"])
            version = row["version"] + 1
            self._write_version(db, tenant, req_id, version, row["cost_centre"], text, built)
            changed = [what for what, given in (("lines", lines), ("justification", justification))
                       if given is not None]
            self._audit(db, tenant, req_id, "updated", version, REQUESTED_BY,
                        f"Changed {' and '.join(changed)}; total"
                        f" {format_zar(sum(x['line_total_zar'] for x in built))}")
            return self._req_dict(self._req_row(db, tenant, req_id))

        return self._run(tenant, update)

    def _write_version(self, db, tenant, req_id, version, cc, text, lines, *, insert=False):
        total = sum(line["line_total_zar"] for line in lines)
        digest = _content_hash(req_id, version, cc, text, lines, total)
        if insert:
            db.execute(
                "INSERT INTO requisitions (tenant, req_id, version, cost_centre, justification,"
                " lines, total, content_hash, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft')",
                (tenant, req_id, version, cc, text, json.dumps(lines), total, digest),
            )
        else:
            db.execute(
                "UPDATE requisitions SET version = ?, justification = ?, lines = ?, total = ?,"
                " content_hash = ? WHERE tenant = ? AND req_id = ?",
                (version, text, json.dumps(lines), total, digest, tenant, req_id),
            )

    def record_approval_event(self, tenant, req_id, version, event, actor, reason=None):
        """Studio-only: audit a decision the server cannot otherwise see (plan ruling 4)."""

        def record(db):
            self._req_row(db, tenant, req_id)
            if event not in STUDIO_EVENTS:
                raise ErpError("invalid", f"Event must be one of: {', '.join(STUDIO_EVENTS)}.")
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                raise ErpError("invalid", "Version must be a positive whole number.")
            if not isinstance(actor, str) or not actor.strip():
                raise ErpError("invalid", "An actor is required.")
            detail = "" if reason is None else str(reason)[:MAX_TEXT]
            self._audit(db, tenant, req_id, event, version, actor.strip(), detail)
            return {"req_id": req_id, "version": version, "event": event, "recorded": True}

        return self._run(tenant, record)

    # ------------------------------------------------------------ submit

    def submit_purchase_order(self, tenant, req_id, version, approval_token, idempotency_key):
        def submit(db):
            row = self._req_row(db, tenant, req_id)
            current = row["version"]

            def refuse(reason):
                self._audit(db, tenant, req_id, "refused", current, "erp", reason)
                raise ErpError("refused", reason)

            if not isinstance(idempotency_key, str) or not idempotency_key.strip():
                raise ErpError("invalid", "An idempotency key is required.")

            # 1. Signature and expiry, on the store's clock.
            try:
                claims = verify(approval_token, self._secret, now=self._clock())
            except TokenError as err:
                refuse(TOKEN_EXPIRED if str(err) == "token expired" else INVALID)

            # 2. Bound to this tenant, requisition, version and content.
            if (claims.get("tenant") != tenant
                    or claims.get("req_id") != req_id
                    or claims.get("version") != current
                    or version != current
                    or claims.get("content_hash") != row["content_hash"]):
                refuse(MISMATCH)

            # 3. Separation of duties.
            approver = claims.get("approver")
            requested_by = claims.get("requested_by")
            if (not isinstance(approver, str) or not approver.strip()
                    or requested_by != REQUESTED_BY or approver == requested_by):
                refuse(INVALID)

            # 4. Policy may only approve at or under the limit.
            if approver == "policy" and row["total"] > self._limit:
                refuse(f"Policy cannot approve orders over {format_zar(self._limit)}.")

            # 5. Already ordered: the same key replays the PO, another key is refused.
            if row["status"] == "ordered":
                if row["idempotency_key"] == idempotency_key:
                    return self._po_dict(db, tenant, row)
                refuse(ALREADY_ORDERED)

            # 6. Every quote still valid.
            now = self._clock()
            if any(now >= line["quote_expires_at_ts"] for line in json.loads(row["lines"])):
                refuse(QUOTE_EXPIRED)

            # 7. Budget at submit time.
            budget = self._budget(db, tenant, row["cost_centre"])
            if row["total"] > budget["remaining"]:
                refuse(f"Over budget: {format_zar(row['total'])} needed,"
                       f" {format_zar(budget['remaining'])} remaining in {row['cost_centre']}.")

            po_number = f"PO-{self._next(db, tenant, 'po_seq'):04d}"
            db.execute(
                "UPDATE budgets SET committed = committed + ? WHERE tenant = ? AND cost_centre = ?",
                (row["total"], tenant, row["cost_centre"]),
            )
            db.execute(
                "UPDATE requisitions SET status = 'ordered', po_number = ?, idempotency_key = ?"
                " WHERE tenant = ? AND req_id = ?",
                (po_number, idempotency_key, tenant, req_id),
            )
            self._audit(db, tenant, req_id, "submitted", current, "erp",
                        f"{po_number} placed for {format_zar(row['total'])}, approved by {approver}"
                        f" ({claims.get('reason', '')})")
            return self._po_dict(db, tenant, self._req_row(db, tenant, req_id))

        return self._run(tenant, submit)

    def _po_dict(self, db, tenant, row):
        return {
            "po_number": row["po_number"],
            "req_id": row["req_id"],
            "version": row["version"],
            "status": row["status"],
            "cost_centre": row["cost_centre"],
            "total_zar": row["total"],
        }
