"""Env-driven fake/real adapter selection for external synchronous ports (§10.2a/§10.2b) —
verified against bold's real `deposit/breb` subcontext: every breb entrypoint resolves its
`BreBAdapter`/pricing adapter through a tiny composition-root factory shaped exactly like

    def get_breb_adapter(provider):
        if context.in_development_ou():
            return fake.FakeBreBAdapter()
        return _MAP_PROVIDER_TO_ADAPTER[provider]()

(`bold/deposit/breb/commons/functions.py::get_breb_adapter`, and the same 3-line recipe
inlined per entrypoint where only one provider exists, e.g.
`deposit/entrypoints/events/breb/breb_keys_cancelation_closed_deposit.py::_get_breb_adapter`).
Two differences from bold's version, both deliberate:

1. bold decides fake-vs-real off a second, raw `OU` env var read directly from `os.environ`
   (`bold.commons.context.in_development_ou()`), parallel to but independent of its real
   settings vocabulary. This codebase already has one settings vocabulary for every
   environment-dependent decision (`Settings.app_env`, `enforcement-and-style.md`/
   `shared-kernel-and-testing.md`) — `Settings.use_fake_external_adapters` (below) reuses it
   instead of adding a second source of truth for "which environment am I in."
2. bold hand-rolls the `if in_development_ou(): return Fake...() else: return Default...()`
   check once per adapter — confirmed against ~20 call sites in `deposit/breb`, no shared
   helper exists there. `get_adapter()` below is this codebase's own small generalization of
   that recipe, not a bold precedent: one function, called from every `_get_*_port()`
   composition-root factory (ARCHITECTURE.md §10.2a/§10.2b), instead of the same four-line
   `if`/`else` copy-pasted into every entrypoint file.

Like bold's version, the fake this returns is not test-only scaffolding: wiring
`_get_pricing_port()`/`_get_user_profile_port()` through `get_adapter()` means a Lambda
actually deployed to DEV/STAGING runs against `FakePricingAdapter`/`FakeUserProfileAdapter`
at runtime, not just under pytest — exactly what lets a dev/staging environment exercise the
full request path without depending on another team's sandbox being up. The same
`Fake<Capability>` classes are also what a unit test imports directly (no env check
involved there — the test constructs the fake itself, see
`tests/unit/backend/commerce/orders/fakes.py`)."""

from collections.abc import Callable

from backend.commons.adapters import settings as settings_module


def get_adapter[T](
    *,
    default_factory: Callable[[], T],
    fake_factory: Callable[[], T],
    settings: settings_module.Settings | None = None,
) -> T:
    """Called from a composition root only — an entrypoint's `_get_*_port()` function
    (ARCHITECTURE.md §9.1/§10.2a/§10.2b) — never from inside `services/`, matching this
    standard's existing rule that a service function never falls back to `port or
    DefaultAdapter()` itself (`anti-patterns-and-design-principles.md` §20's own entry on
    that exact mistake). `default_factory`/`fake_factory` are zero-arg callables (usually
    just the class itself, e.g. `HttpPricingAdapter`) so this stays agnostic to whatever
    constructor arguments either adapter needs."""
    settings = settings or settings_module.get_settings()
    if settings.use_fake_external_adapters:
        return fake_factory()
    return default_factory()
