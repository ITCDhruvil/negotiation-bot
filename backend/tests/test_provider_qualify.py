import os

from app.config import get_settings
from app.llm.provider import (
    MockProvider,
    OpenAIProvider,
    build_provider,
    is_reasoning_model,
    openai_completion_kwargs,
)
from app.orchestrator.qualify import (
    apply_qualification,
    can_proceed_without_contact,
    is_qualified,
    looks_like_contact_refusal,
)

from tests.test_deal_engine import make_session


def test_name_here_plus_email_qualifies():
    session = make_session(vendor_rep_name=None, vendor_rep_contact=None)
    session = apply_qualification(session, "Mehta here, mehta@valeo.example. We're firm on this line.")
    assert session.vendor_rep_name == "Mehta"
    assert session.vendor_rep_contact == "mehta@valeo.example"
    assert is_qualified(session) is True


def test_detects_contact_refusal():
    assert looks_like_contact_refusal("i cannot give you that") is True
    assert looks_like_contact_refusal("I won't share my email") is True
    assert looks_like_contact_refusal("good morning") is False


def test_name_and_company_after_refusal_is_enough_to_proceed():
    session = make_session(vendor_rep_name=None, vendor_rep_contact=None, contact_refusal_count=1)
    session = apply_qualification(session, "I'm Arjun from Yazaki India")
    assert session.vendor_rep_name == "Arjun"
    assert "Yazaki" in (session.vendor_company or "")
    assert is_qualified(session) is False
    assert can_proceed_without_contact(session) is True


def test_second_bare_no_after_refusal_proceeds():
    from app.orchestrator.qualify import can_proceed_without_contact, is_bare_decline

    assert is_bare_decline("no") is True
    session = make_session(vendor_rep_name=None, vendor_rep_contact=None, contact_refusal_count=1)
    session.contact_refusal_count += 1  # second decline
    assert can_proceed_without_contact(session) is True
    session = make_session(vendor_rep_name=None, vendor_rep_contact=None, contact_refusal_count=2)
    assert can_proceed_without_contact(session) is True


def test_build_provider_honours_test_harness_mock(monkeypatch):
    monkeypatch.setenv("ARIA_ALLOW_MOCK", "1")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    get_settings.cache_clear()
    assert isinstance(build_provider(), MockProvider)


def test_live_mock_is_ignored_when_openai_key_exists(monkeypatch):
    monkeypatch.delenv("ARIA_ALLOW_MOCK", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")
    get_settings.cache_clear()
    try:
        provider = build_provider()
        assert isinstance(provider, OpenAIProvider)
        assert provider.name == "openai"
    finally:
        get_settings.cache_clear()
        os.environ["ARIA_ALLOW_MOCK"] = "1"
        os.environ["LLM_PROVIDER"] = "mock"


def test_reasoning_models_use_completion_token_cap_and_effort():
    assert is_reasoning_model("o4-mini")
    assert is_reasoning_model("gpt-5.4-mini")
    assert not is_reasoning_model("gpt-4o")
    kwargs = openai_completion_kwargs("o4-mini", max_output=512, tools=True, reasoning_effort="medium")
    assert kwargs["model"] == "o4-mini"
    assert kwargs["max_completion_tokens"] > 512
    assert kwargs["reasoning_effort"] == "medium"
    assert "max_tokens" not in kwargs


def test_chat_model_keeps_max_tokens():
    kwargs = openai_completion_kwargs("gpt-4o", max_output=400, stream=True)
    assert kwargs["max_tokens"] == 400
    assert kwargs["stream"] is True
    assert "reasoning_effort" not in kwargs


def test_gpt54_tools_force_effort_none():
    kwargs = openai_completion_kwargs("gpt-5.4", max_output=512, tools=True, reasoning_effort="high")
    assert kwargs["reasoning_effort"] == "none"
