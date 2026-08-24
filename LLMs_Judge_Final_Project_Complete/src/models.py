"""Single-model 4-bit generation support for the Pipeline lane."""

from __future__ import annotations

from dataclasses import dataclass
import gc
import time
from typing import Any


@dataclass(frozen=True)
class GenerationOutput:
    """One generated completion with token and latency telemetry."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    elapsed_seconds: float
    model_version: str


class FourBitModel:
    """Load one causal language model at a time and release its memory explicitly."""

    def __init__(self, model_id: str, quantization: dict[str, Any], runtime: dict[str, Any]):
        self.model_id = model_id
        self.quantization = quantization
        self.runtime = runtime
        self.model: Any | None = None
        self.tokenizer: Any | None = None
        self.torch: Any | None = None
        self.version = model_id

    def load(self) -> None:
        """Load the configured model using bitsandbytes 4-bit NF4 quantization."""
        try:
            import torch
            import transformers
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        except ImportError as exc:  # pragma: no cover - depends on the notebook image
            raise RuntimeError(
                "Install torch, transformers, accelerate, and bitsandbytes before running the Pipeline."
            ) from exc

        if self.quantization.get("load_in_4bit") is not True:
            raise ValueError("The Pipeline specification requires load_in_4bit=true.")
        dtype_name = str(self.quantization["bnb_4bit_compute_dtype"])
        compute_dtype = getattr(torch, dtype_name, None)
        if compute_dtype is None:
            raise ValueError(f"Unknown torch dtype: {dtype_name}")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=str(self.quantization["bnb_4bit_quant_type"]),
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=bool(self.quantization["bnb_4bit_use_double_quant"]),
        )
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        if self.tokenizer.pad_token_id is None and self.tokenizer.eos_token is not None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "left"
        model_kwargs = {
            "quantization_config": bnb_config,
            "device_map": self.runtime["device_map"],
        }
        self.model = AutoModelForCausalLM.from_pretrained(self.model_id, **model_kwargs)
        self.model.eval()
        self.torch = torch
        commit = getattr(self.model.config, "_commit_hash", None)
        self.version = f"{self.model_id}@{commit or 'unknown'};transformers={transformers.__version__}"

    def generate(self, prompt: str, decoding: dict[str, Any]) -> GenerationOutput:
        """Generate one completion and return it without prompt echo."""
        if self.model is None or self.tokenizer is None or self.torch is None:
            raise RuntimeError("The model must be loaded before generation.")
        # The retry decoding settings enable sampling only for the configured retry.
        do_sample = decoding.get("do_sample") is True
        max_new_tokens = int(decoding.get("max_new_tokens", 0))
        if max_new_tokens <= 0:
            raise ValueError("decoding.max_new_tokens must be a positive integer.")

        inputs = self._tokenize(prompt)
        inputs = {name: value.to(self._input_device()) for name, value in inputs.items()}
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        started = time.perf_counter()
        generation_config = getattr(self.model, "generation_config", None)
        pad_token_id = getattr(generation_config, "pad_token_id", None)
        if pad_token_id is None:
            pad_token_id = self.tokenizer.pad_token_id
        generation_kwargs = {
            "do_sample": do_sample,
            "max_new_tokens": max_new_tokens,
            "pad_token_id": pad_token_id,
        }
        if do_sample:
            temperature = float(decoding.get("temperature", 0))
            if temperature <= 0:
                raise ValueError("Sampled decoding requires a positive temperature.")
            generation_kwargs["temperature"] = temperature
        if getattr(generation_config, "eos_token_id", None) is None:
            generation_kwargs["eos_token_id"] = self.tokenizer.eos_token_id
        with self.torch.inference_mode():
            tokens = self.model.generate(**inputs, **generation_kwargs)
        elapsed = time.perf_counter() - started
        completion_ids = tokens[0][prompt_tokens:]
        return GenerationOutput(
            text=self.tokenizer.decode(completion_ids, skip_special_tokens=True),
            prompt_tokens=prompt_tokens,
            completion_tokens=int(completion_ids.shape[-1]),
            elapsed_seconds=elapsed,
            model_version=self.version,
        )

    def unload(self) -> None:
        """Release model memory before another model is loaded."""
        self.model = None
        self.tokenizer = None
        gc.collect()
        if self.torch is not None and self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()
        self.torch = None

    def _tokenize(self, prompt: str) -> dict[str, Any]:
        if self.runtime.get("use_chat_template") and getattr(self.tokenizer, "chat_template", None):
            return self.tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
            )
        return self.tokenizer(prompt, return_tensors="pt")

    def _input_device(self) -> Any:
        device_map = getattr(self.model, "hf_device_map", {})
        for device in device_map.values():
            if isinstance(device, int):
                return self.torch.device(f"cuda:{device}")
            if isinstance(device, str) and device not in {"cpu", "disk"}:
                return self.torch.device(device)
        return next(self.model.parameters()).device

    def __enter__(self) -> "FourBitModel":
        self.load()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.unload()
