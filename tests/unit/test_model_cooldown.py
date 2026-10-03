# -*- coding: utf-8 -*-
"""Unit tests for aigw.model_cooldown."""

from aigw.model_cooldown import ModelCooldown, is_transient_status, parse_retry_after


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _cd(base: float = 10, max_: float = 300) -> tuple[ModelCooldown, _Clock]:
    clock = _Clock()
    return ModelCooldown(base, max_, clock=clock), clock


class TestTransientStatus:
    def test_transient(self):
        for code in (408, 425, 429, 500, 502, 503, 504, 529):
            assert is_transient_status(code)

    def test_deterministic(self):
        for code in (400, 401, 403, 404, 413, 422):
            assert not is_transient_status(code)


class TestParseRetryAfter:
    def test_seconds(self):
        assert parse_retry_after("30") == 30.0

    def test_http_date(self):
        # 2015-10-21 07:28:00 GMT = 1445412480
        assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", now=1445412480 - 15) == 15.0

    def test_missing_or_garbage(self):
        assert parse_retry_after(None) is None
        assert parse_retry_after("") is None
        assert parse_retry_after("soon") is None

    def test_negative_clamped(self):
        assert parse_retry_after("-5") == 0.0


class TestModelCooldown:
    def test_exponential_backoff_capped(self):
        cd, _ = _cd(base=10, max_=35)
        assert cd.record_failure("m") == 10
        assert cd.record_failure("m") == 20
        assert cd.record_failure("m") == 35
        assert cd.record_failure("m") == 35

    def test_expires(self):
        cd, clock = _cd()
        cd.record_failure("m")
        assert cd.remaining("m") == 10
        clock.t += 10
        assert cd.remaining("m") == 0

    def test_success_resets_streak(self):
        cd, _ = _cd()
        cd.record_failure("m")
        cd.record_failure("m")
        cd.record_success("m")
        assert cd.remaining("m") == 0
        assert cd.record_failure("m") == 10

    def test_old_failure_starts_new_streak(self):
        cd, clock = _cd(base=10, max_=60)
        cd.record_failure("m")
        cd.record_failure("m")  # 20s
        clock.t += 20 + 61
        assert cd.record_failure("m") == 10

    def test_retry_after_overrides_and_is_capped(self):
        cd, _ = _cd(base=10, max_=100)
        assert cd.record_failure("m", retry_after=50) == 50
        assert cd.record_failure("m", retry_after=1000) == 100

    def test_order_skips_cooling_models(self):
        cd, _ = _cd()
        cd.record_failure("a")
        assert cd.order(["a", "b", "c"]) == ["b", "c"]

    def test_order_all_cooling_probes_soonest(self):
        cd, _ = _cd()
        cd.record_failure("a", retry_after=50)
        cd.record_failure("b", retry_after=20)
        assert cd.order(["a", "b"]) == ["b"]

    def test_order_single_candidate_untouched(self):
        cd, _ = _cd()
        cd.record_failure("a")
        assert cd.order(["a"]) == ["a"]

    def test_disabled_when_base_zero(self):
        cd, _ = _cd(base=0)
        assert cd.record_failure("a") == 0
        assert cd.order(["a", "b"]) == ["a", "b"]
