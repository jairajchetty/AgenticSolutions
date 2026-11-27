import pytest

from agentic_solutions.web.threads import ThreadStore, once


def test_get_by_another_session_raises_keyerror():
    store = ThreadStore()
    rec = store.create("s1", "qa", "offline")
    assert store.get(rec.id, "s1") is rec
    with pytest.raises(KeyError):
        store.get(rec.id, "s2")
    with pytest.raises(KeyError):
        store.get("missing", "s1")


def test_one_active_run_per_session():
    store = ThreadStore()
    assert store.begin_run("s1") is True
    assert store.begin_run("s1") is False      # second run while the first is active -> API 409
    assert store.begin_run("s2") is True       # other sessions are unaffected
    store.end_run("s1")
    assert store.begin_run("s1") is True


def test_release_is_once_only_so_a_late_release_cannot_free_the_next_run():
    store = ThreadStore()
    assert store.begin_run("s1")
    release_a = once(lambda: store.end_run("s1"))
    release_a()                                # run A's stream finishes and releases
    assert store.begin_run("s1")               # run B claims the slot
    release_a()                                # A's late second release (on_close) is a no-op
    assert store.begin_run("s1") is False      # B still holds the slot
