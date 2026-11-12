"""NVIDIA NIM provider — OpenAI-compatible hosted chat API."""

import time

from src.config import get_active_config
from src.services.llm.base import BaseProvider


class NvidiaProvider(BaseProvider):
    @property
    def provider_name(self) -> str:
        return "nvidia"

    def _do_generate(self, system_prompt: str, user_prompt: str, call_type: str) -> str:
        config = get_active_config()
        if not config.nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY is not set in .env")

        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        payload = {
            "model": config.nvidia_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.generation_temperature(call_type),
            "max_tokens": self.generation_max_tokens(call_type),
            "stream": False,
        }
        start = time.monotonic()
        call_id = self._log_request_sent(call_type=call_type, url=url, request_body=payload)
        response = self._client_instance.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {config.nvidia_api_key}"},
        )
        duration = (time.monotonic() - start) * 1000
        self._check_response(response)
        data = response.json()
        self._log_request_received(
            call_id=call_id,
            call_type=call_type,
            url=url,
            response_body=data,
            status_code=response.status_code,
            duration_ms=duration,
        )

        choices = data.get("choices", [])
        content = choices[0].get("message", {}).get("content") if choices else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("NVIDIA returned no content")
        content = content.strip()
        # Gemma 4 may include an empty thought block even with thinking disabled.
        if config.nvidia_model.startswith("google/gemma-4") and content.startswith("<|channel>thought"):
            content = content.partition("<channel|>")[2]
        if not content.strip():
            raise RuntimeError("NVIDIA returned no content")
        return content.strip()
