from __future__ import annotations

import pytest

from domain.providers import normalize_agent


def test_known_agent_alone_validates_and_lowercases():
    identity = normalize_agent("Claude-Code")

    assert identity.agent_id == "claude-code"
    assert identity.provider == "anthropic"
    assert identity.model_family is None
    assert identity.model_version is None
    assert identity.model_name is None


def test_anthropic_triple_derives_canonical_slug():
    identity = normalize_agent(
        "claude-code",
        model_family="claude-opus",
        model_version="4-7",
    )

    assert identity.provider == "anthropic"
    assert identity.model_family == "claude-opus"
    assert identity.model_version == "4-7"
    assert identity.model_name == "claude-opus-4-7"


def test_openai_triple_derives_canonical_slug():
    identity = normalize_agent(
        "codex",
        model_family="gpt",
        model_version="5.5",
    )

    assert identity.provider == "openai"
    assert identity.model_name == "gpt-5.5"


def test_unknown_agent_id_raises():
    with pytest.raises(ValueError, match="Unknown agent_id"):
        normalize_agent("agent_made_up")


def test_family_for_wrong_provider_raises():
    with pytest.raises(ValueError, match="not valid for agent"):
        # gpt is OpenAI's family; claude-code is an Anthropic harness.
        normalize_agent("claude-code", model_family="gpt", model_version="5.5")


def test_anthropic_version_pattern_rejects_dot_version():
    with pytest.raises(ValueError, match="version"):
        normalize_agent("claude-code", model_family="claude-opus", model_version="5.5")


def test_family_without_version_raises():
    with pytest.raises(ValueError, match="provided together"):
        normalize_agent("claude-code", model_family="claude-opus")


def test_version_without_family_raises():
    with pytest.raises(ValueError, match="provided together"):
        normalize_agent("claude-code", model_version="4-7")


def test_dated_anthropic_version_accepted():
    identity = normalize_agent(
        "claude-code",
        model_family="claude-haiku",
        model_version="4-5-20251001",
    )

    assert identity.model_name == "claude-haiku-4-5-20251001"
