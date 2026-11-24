import pytest

from agentic_solutions.common.approval_tokens import (
    TOKEN_TTL_S,
    TokenError,
    issue,
    verify,
)

SECRET = b"s3cret"
CLAIMS = {
    "req_id": "r1",
    "version": 1,
    "content_hash": "abc",
    "tenant": "t1",
    "approver": "visitor:0123456789ab",
    "requested_by": "agent",
    "reason": "approved",
}


def test_round_trip_returns_claims_with_exp():
    tok = issue(CLAIMS, SECRET, now=1000.0)
    out = verify(tok, SECRET, now=1001.0)
    assert out == {**CLAIMS, "exp": 1000.0 + TOKEN_TTL_S}


def test_tampered_payload_or_signature_is_bad_signature():
    tok = issue(CLAIMS, SECRET, now=1000.0)
    payload, sig = tok.split(".")
    flipped_sig = sig[:-2] + ("AA" if not sig.endswith("AA") else "BB")
    other = issue({**CLAIMS, "tenant": "t2"}, SECRET, now=1000.0).split(".")[0]
    for bad in (f"{payload}.{flipped_sig}", f"{other}.{sig}"):
        with pytest.raises(TokenError, match="bad signature"):
            verify(bad, SECRET, now=1001.0)


def test_wrong_secret_is_bad_signature():
    tok = issue(CLAIMS, SECRET, now=1000.0)
    with pytest.raises(TokenError, match="bad signature"):
        verify(tok, b"other", now=1001.0)


def test_expired_token():
    tok = issue(CLAIMS, SECRET, ttl_s=10, now=1000.0)
    assert verify(tok, SECRET, now=1009.0)["tenant"] == "t1"
    with pytest.raises(TokenError, match="token expired"):
        verify(tok, SECRET, now=1011.0)


@pytest.mark.parametrize("bad", ["", "abc", "a.b.c"])
def test_malformed_token(bad):
    with pytest.raises(TokenError, match="malformed token"):
        verify(bad, SECRET)


def test_issue_requires_all_claims():
    for key in CLAIMS:
        partial = {k: v for k, v in CLAIMS.items() if k != key}
        with pytest.raises(ValueError, match=key):
            issue(partial, SECRET)


def test_non_canonical_signature_is_rejected():
    tok = issue(CLAIMS, SECRET, now=1000.0)
    payload, sig = tok.split(".")
    for bad_sig in (sig + "=", sig[:10] + "!" + sig[10:], sig[:10] + "\n" + sig[10:]):
        with pytest.raises(TokenError, match="bad signature|malformed token"):
            verify(f"{payload}.{bad_sig}", SECRET, now=1001.0)


def test_claim_key_order_does_not_change_token():
    reordered = dict(reversed(list(CLAIMS.items())))
    assert issue(CLAIMS, SECRET, now=5.0) == issue(reordered, SECRET, now=5.0)


def test_now_equal_to_exp_is_expired():
    tok = issue(CLAIMS, SECRET, ttl_s=10, now=1000.0)
    with pytest.raises(TokenError, match="token expired"):
        verify(tok, SECRET, now=1010.0)
