from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol

from app.config import get_settings
from app.llm.tools import TOOLS, openai_tools

logger = logging.getLogger("aria.llm")


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        hints: dict[str, Any] | None = None,
    ) -> LLMTurn: ...

    async def stream_text(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]: ...


def is_reasoning_model(model: str) -> bool:
    name = (model or "").lower().strip()
    return name.startswith(("o1", "o3", "o4", "gpt-5")) or "reason" in name


def chat_completions_tools_need_effort_none(model: str) -> bool:
    """GPT-5.4+ Chat Completions only allow tools when reasoning_effort is none."""
    return (model or "").lower().startswith("gpt-5.4")


def openai_completion_kwargs(
    model: str,
    *,
    max_output: int,
    tools: bool = False,
    stream: bool = False,
    reasoning_effort: str = "medium",
) -> dict[str, Any]:
    """Chat Completions params. Reasoning models cannot take max_tokens."""
    kwargs: dict[str, Any] = {"model": model}
    if stream:
        kwargs["stream"] = True
    if is_reasoning_model(model):
        # Reasoning tokens count against the cap; keep headroom so the tool call is not truncated.
        kwargs["max_completion_tokens"] = max_output + (2048 if tools else 512)
        if tools and chat_completions_tools_need_effort_none(model):
            kwargs["reasoning_effort"] = "none"
        elif reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
    else:
        kwargs["max_tokens"] = max_output
    return kwargs


def _model_unavailable(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in ("model_not_found", "does not exist", "does not have access", "invalid model")
    )


class MockProvider:
    """Deterministic stand-in for automated tests.

    Live/demo sessions must not use this when real credentials exist.
    """

    name = "mock"
    chat_model = "mock"
    reasoning_model = "mock"

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        hints: dict[str, Any] | None = None,
    ) -> LLMTurn:
        hints = hints or {}
        stage = hints.get("stage", "")
        authorized = hints.get("authorized_offer")

        if hints.get("force_escalate"):
            return LLMTurn(
                text="",
                tool_calls=[ToolCall(name="escalate_to_human", input={"reason": hints.get("escalate_reason", "impasse")})],
            )

        if stage in {"greet_and_disclose", "qualify", "agreement", "handoff"}:
            return LLMTurn(text="")

        if authorized is None:
            return LLMTurn(text="What would make this work for you today?")

        tactic = hints.get("selected_tactic") or (
            "anchoring_hold" if stage == "open_offer" else "competitive_bid"
        )
        if hints.get("near_ceiling") and tactic not in {
            "lead_time_trade",
            "warranty_trade",
            "calibrated_question",
            "clarify_hold",
            "redirect",
            "anchoring_hold",
        }:
            tactic = "payment_terms_trade"
        intent = str(hints.get("interpreted_intent") or "counter_offer")
        reasoning = str(
            hints.get("reasoning")
            or (
                f"Vendor intent is {intent} at {hints.get('signal_confidence', 'medium')} confidence; "
                f"respond with {tactic} rather than a stage script."
            )
        )
        return LLMTurn(
            text="",
            tool_calls=[
                ToolCall(
                    name="propose_price",
                    input={
                        "reasoning": reasoning,
                        "interpreted_intent": intent,
                        "tactic": tactic,
                        "price": int(authorized),
                    },
                )
            ],
        )

    async def stream_text(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        if False:
            yield ""
        return


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model
        self.chat_model = self._model
        self.reasoning_model = self._model

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        hints: dict[str, Any] | None = None,
    ) -> LLMTurn:
        response = await self._client.messages.create(
            model=self._model,
            system=system,
            messages=messages,
            tools=TOOLS,
            max_tokens=512,
        )
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(name=block.name, input=dict(block.input)))
        return LLMTurn(text="".join(text_parts).strip(), tool_calls=tool_calls)

    async def stream_text(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self._model,
            system=system,
            messages=messages,
            max_tokens=400,
        ) as stream:
            async for text in stream.text_stream:
                yield text


def _openai_turn_from_choice(choice) -> LLMTurn:
    tool_calls: list[ToolCall] = []
    for call in choice.tool_calls or []:
        tool_calls.append(
            ToolCall(
                name=call.function.name,
                input=json.loads(call.function.arguments or "{}"),
            )
        )
    return LLMTurn(text=(choice.content or "").strip(), tool_calls=tool_calls)


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        settings = get_settings()
        from app.finetune.active import resolved_chat_model

        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.chat_model = resolved_chat_model(settings.openai_model)
        self.reasoning_model = (settings.openai_reasoning_model or "").strip() or settings.openai_model
        self.reasoning_effort = (settings.openai_reasoning_effort or "medium").strip()
        self._model = self.chat_model

    async def _create(self, model: str, *, payload: list[dict[str, str]], tools: bool, max_output: int, stream: bool = False):
        kwargs = openai_completion_kwargs(
            model,
            max_output=max_output,
            tools=tools,
            stream=stream,
            reasoning_effort=self.reasoning_effort,
        )
        if tools:
            kwargs["tools"] = openai_tools()
        return await self._client.chat.completions.create(messages=payload, **kwargs)

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        hints: dict[str, Any] | None = None,
    ) -> LLMTurn:
        payload = [{"role": "system", "content": system}, *messages]
        model = self.reasoning_model
        try:
            response = await self._create(model, payload=payload, tools=True, max_output=512)
        except Exception as exc:
            if model != self.chat_model and _model_unavailable(exc):
                logger.warning("Reasoning model %s unavailable; using %s for this turn", model, self.chat_model)
                response = await self._create(self.chat_model, payload=payload, tools=True, max_output=512)
            else:
                raise
        return _openai_turn_from_choice(response.choices[0].message)

    async def stream_text(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        payload = [{"role": "system", "content": system}, *messages]
        stream = await self._create(self.chat_model, payload=payload, tools=False, max_output=400, stream=True)
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


class AzureOpenAIProvider:
    name = "azure"

    def __init__(self) -> None:
        from openai import AsyncAzureOpenAI

        settings = get_settings()
        self._client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )
        self._deployment = settings.azure_openai_deployment
        self.chat_model = self._deployment
        self.reasoning_model = self._deployment

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        hints: dict[str, Any] | None = None,
    ) -> LLMTurn:
        payload = [{"role": "system", "content": system}, *messages]
        response = await self._client.chat.completions.create(
            model=self._deployment,
            messages=payload,
            tools=openai_tools(),
            max_tokens=512,
        )
        return _openai_turn_from_choice(response.choices[0].message)

    async def stream_text(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        payload = [{"role": "system", "content": system}, *messages]
        stream = await self._client.chat.completions.create(
            model=self._deployment,
            messages=payload,
            max_tokens=400,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


_ALIASES = {"claude": "anthropic", "gpt": "openai"}


def _in_test_harness() -> bool:
    return os.environ.get("ARIA_ALLOW_MOCK") == "1"


def available_real_providers(settings=None) -> list[str]:
    settings = settings or get_settings()
    found: list[str] = []
    if settings.openai_api_key:
        found.append("openai")
    if settings.anthropic_api_key:
        found.append("anthropic")
    if settings.azure_openai_api_key and settings.azure_openai_endpoint:
        found.append("azure")
    return found


def _instantiate(name: str) -> LLMProvider:
    if name == "openai":
        return OpenAIProvider()
    if name == "anthropic":
        return AnthropicProvider()
    if name == "azure":
        return AzureOpenAIProvider()
    raise RuntimeError(f"Unknown provider {name}")


def provider_models(provider: LLMProvider) -> tuple[str, str]:
    chat = getattr(provider, "chat_model", "") or ""
    reason = getattr(provider, "reasoning_model", "") or chat
    return chat, reason


def build_provider() -> LLMProvider:
    settings = get_settings()
    requested = (settings.llm_provider or "auto").lower().strip()
    requested = _ALIASES.get(requested, requested)
    available = available_real_providers(settings)

    if requested == "mock":
        if _in_test_harness():
            logger.info("LLM provider=mock (test harness)")
            return MockProvider()
        if available:
            chosen = available[0]
            logger.warning(
                "LLM_PROVIDER=mock ignored because credentials exist for %s; using %s for this live session",
                ",".join(available),
                chosen,
            )
            return _instantiate(chosen)
        logger.critical(
            "ARIA LLM PROVIDER=mock — no API credentials. Replies are fixtures, not a model."
        )
        return MockProvider()

    if requested == "auto":
        if available:
            return _instantiate(available[0])
        if _in_test_harness():
            logger.info("LLM provider=mock (auto, test harness, no credentials)")
            return MockProvider()
        raise RuntimeError(
            "No LLM credentials. Set OPENAI_API_KEY (or ANTHROPIC_API_KEY / Azure), "
            "or set ARIA_ALLOW_MOCK=1 only for tests."
        )

    if requested in {"openai", "anthropic", "azure"}:
        if requested in available:
            return _instantiate(requested)
        if available:
            logger.warning(
                "LLM_PROVIDER=%s is missing credentials; using %s instead",
                requested,
                available[0],
            )
            return _instantiate(available[0])
        if _in_test_harness():
            return MockProvider()
        raise RuntimeError(f"LLM_PROVIDER={requested} but credentials are missing.")

    raise RuntimeError(f"Unknown LLM_PROVIDER={requested!r}. Use auto|openai|claude|azure|mock.")
