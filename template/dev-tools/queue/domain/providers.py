"""Provider registry for agent / model identity validation.

The queue captures three pieces of agent identity per session:

- ``agent_id`` — the *harness* (e.g. ``claude-code``, ``codex``)
- ``model_family`` — the *model line* (e.g. ``claude-opus``, ``gpt``)
- ``model_version`` — the *release* within that family (e.g. ``4-7``,
  ``5.5``, ``5-codex``)

Each provider declares which agent_ids and model_families belong to it,
plus an optional version regex. ``normalize_agent`` validates the
triple, lowercases everything, and synthesizes the canonical
``model_name`` slug (``{family}-{version}``).

The registry is a flat tuple of frozen records. To add a new provider
or harness, append a ``ProviderAdapter`` here. Per-provider behavior
beyond identity normalization (commands, output parsing, MCP tool
naming) does not belong in this module — extract a richer adapter
class only when that demand actually arrives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    agent_id: str
    provider: str
    model_family: str | None
    model_version: str | None
    model_name: str | None


@dataclass(frozen=True, slots=True)
class ProviderAdapter:
    provider: str
    agent_ids: frozenset[str]
    model_families: frozenset[str]
    version_pattern: re.Pattern[str] | None = None


KNOWN_PROVIDERS: tuple[ProviderAdapter, ...] = (
    ProviderAdapter(
        provider="anthropic",
        agent_ids=frozenset({"claude-code", "claude-desktop"}),
        model_families=frozenset({"claude-opus", "claude-sonnet", "claude-haiku"}),
        # 4-7, 4-6, 4-5-20251001 — major-minor with optional date suffix.
        version_pattern=re.compile(r"^\d+-\d+(-\d{8})?$"),
    ),
    ProviderAdapter(
        provider="openai",
        agent_ids=frozenset({"codex", "cursor"}),
        model_families=frozenset({"gpt"}),
        # 5.5, 5-codex, 4o, 4-turbo — permissive within alphanumerics + . -.
        version_pattern=re.compile(r"^[a-z0-9.\-]+$"),
    ),
)


def _adapter_for(agent_id: str) -> ProviderAdapter:
    for adapter in KNOWN_PROVIDERS:
        if agent_id in adapter.agent_ids:
            return adapter
    known = sorted({a for adapter in KNOWN_PROVIDERS for a in adapter.agent_ids})
    raise ValueError(
        f"Unknown agent_id {agent_id!r}; known agents: {known}. "
        f"Add a ProviderAdapter to domain/providers.py if introducing a "
        f"new harness."
    )


def normalize_agent(
    agent_id: str,
    model_family: str | None = None,
    model_version: str | None = None,
) -> AgentIdentity:
    """Validate and lowercase the agent / model triple.

    Raises ``ValueError`` on:
    - unknown ``agent_id``
    - ``model_family`` not registered for the agent's provider
    - ``model_version`` not matching the provider's version pattern
    - one of ``model_family`` / ``model_version`` provided without the other

    ``model_family`` and ``model_version`` are optional as a pair; passing
    neither validates only the agent_id and returns ``model_*=None``.
    """
    agent_id_lower = agent_id.lower()
    adapter = _adapter_for(agent_id_lower)

    if (model_family is None) != (model_version is None):
        raise ValueError(
            "model_family and model_version must be provided together "
            f"(got model_family={model_family!r}, "
            f"model_version={model_version!r})."
        )

    if model_family is None:
        return AgentIdentity(
            agent_id=agent_id_lower,
            provider=adapter.provider,
            model_family=None,
            model_version=None,
            model_name=None,
        )

    family_lower = model_family.lower()
    version_lower = model_version.lower() if model_version is not None else None
    assert version_lower is not None  # narrowed by the paired check above.

    if family_lower not in adapter.model_families:
        raise ValueError(
            f"Model family {family_lower!r} is not valid for agent "
            f"{agent_id_lower!r} (provider={adapter.provider}); valid "
            f"families: {sorted(adapter.model_families)}."
        )

    if adapter.version_pattern is not None and not adapter.version_pattern.match(
        version_lower
    ):
        raise ValueError(
            f"Model version {version_lower!r} doesn't match the expected "
            f"shape for provider {adapter.provider} "
            f"({adapter.version_pattern.pattern})."
        )

    return AgentIdentity(
        agent_id=agent_id_lower,
        provider=adapter.provider,
        model_family=family_lower,
        model_version=version_lower,
        model_name=f"{family_lower}-{version_lower}",
    )
