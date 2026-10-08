"""
Local Finnish model provider (TurkuNLP GPT-3 Finnish small).

Needs the optional ML dependencies (`requirements-ml.txt`) and enough memory to
load the model, so it is disabled on small hosts with DISABLE_LOCAL_MODEL=true.
"""
from functools import lru_cache
from typing import Any

from starlette.concurrency import run_in_threadpool

from aibot.llm.base import LLMProvider, LLMResponse, Message, ProviderNotConfigured, ToolSpec
from aibot.settings import env_bool

MODEL_NAME = "TurkuNLP/gpt3-finnish-small"


@lru_cache(maxsize=1)
def _load_model() -> tuple[Any, Any, str]:
    """Load and cache the tokenizer and model on first use."""
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)  # nosec B615 - trusted public HuggingFace model, revision pinning not required
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)  # nosec B615 - trusted public HuggingFace model, revision pinning not required
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    device = "cpu"
    return tokenizer, model.to(device), device


class LocalProvider(LLMProvider):
    """Plain text completion with a small local model (no tools, no embeddings)."""

    name = "local"
    supports_tools = False
    supports_embeddings = False

    def is_configured(self) -> bool:
        return not env_bool("DISABLE_LOCAL_MODEL")

    async def generate(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        json_output: bool = False,
    ) -> LLMResponse:
        if not self.is_configured():
            raise ProviderNotConfigured("Local model is disabled. Use provider=puter_ai or vertex_ai instead.")
        if tools:
            raise ProviderNotConfigured("The local model does not support tool calling.")
        prompt = "\n\n".join(m.content for m in messages)
        text = await run_in_threadpool(_complete, prompt, temperature if temperature is not None else 0.8)
        return LLMResponse(text=text)


def _complete(prompt: str, temperature: float) -> str:
    """Generate a continuation for the prompt."""
    try:
        tokenizer, model, device = _load_model()
    except ImportError as exc:
        raise ProviderNotConfigured(
            "ML dependencies are not installed. Build with INCLUDE_ML_DEPS=1."
        ) from exc

    input_ids = tokenizer(prompt, return_tensors="pt").to(device).input_ids
    outputs = model.generate(
        input_ids,
        max_new_tokens=300,
        temperature=temperature,
        top_p=0.92,
        do_sample=True,
        repetition_penalty=1.1,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    generated_ids = outputs[0]
    new_tokens = generated_ids[input_ids.shape[-1]:]
    if new_tokens.numel() == 0:
        new_tokens = generated_ids
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
