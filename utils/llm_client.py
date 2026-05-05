"""
Multi-provider LLM client for manga layout decisions.
Supports: MiniMax, OpenAI (compatible), Ollama (local).
"""

import json
import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional
from enum import Enum

import requests

# mmx CLI path
MMX_CLI = os.path.expanduser("~/.npm-global/bin/mmx")

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    MINIMAX = "minimax"
    MINIMAX_CLI = "minimax_cli"
    OPENAI = "openai"
    OLLAMA = "ollama"


DEFAULT_PROVIDER = LLMProvider.MINIMAX_CLI  # mmx CLI doesn't need API key
DEFAULT_MODEL = "MiniMax-M2"

MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OLLAMA_API_URL = "http://localhost:11434/api/chat"


class LLMClient:
    """
    Unified LLM client supporting multiple providers.
    Falls back gracefully when API key is not set.
    """

    def __init__(
        self,
        provider: LLMProvider = DEFAULT_PROVIDER,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._provider = provider
        self._api_url = api_url or self._default_url(provider)
        self._api_key = api_key or self._get_env_key(provider)
        self._model = model or DEFAULT_MODEL if provider == LLMProvider.MINIMAX else "gpt-4o-mini"

        if provider == LLMProvider.OLLAMA:
            self._model = model or "llama3.2"

        logger.info(f"LLMClient: provider={provider.value}, model={self._model}, url={self._api_url[:50]}...")

    def _default_url(self, provider: LLMProvider) -> str:
        if provider == LLMProvider.MINIMAX:
            return MINIMAX_API_URL
        elif provider == LLMProvider.OPENAI:
            return OPENAI_API_URL
        else:
            return OLLAMA_API_URL

    def _get_env_key(self, provider: LLMProvider) -> str:
        if provider == LLMProvider.MINIMAX:
            return os.environ.get("MINIMAX_API_KEY", "")
        elif provider == LLMProvider.OPENAI:
            return os.environ.get("OPENAI_API_KEY", "")
        return ""

    def is_available(self) -> bool:
        """Check if LLM is available (has API key or Ollama is running or mmx CLI exists)."""
        if self._provider == LLMProvider.OLLAMA:
            return True  # Ollama runs locally, always available
        if self._provider == LLMProvider.MINIMAX_CLI:
            return os.path.isfile(MMX_CLI)  # Check if mmx CLI exists
        return bool(self._api_key)

    def set_provider(self, provider: LLMProvider, api_key: Optional[str] = None) -> None:
        """Switch LLM provider."""
        self._provider = provider
        self._api_url = self._default_url(provider)
        if api_key:
            self._api_key = api_key
        else:
            self._api_key = self._get_env_key(provider)
        self._model = DEFAULT_MODEL if provider == LLMProvider.MINIMAX else "gpt-4o-mini"
        if provider == LLMProvider.OLLAMA:
            self._model = "llama3.2"
        logger.info(f"Switched to provider: {provider.value}")

    def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> Optional[str]:
        """
        Generic chat completion.
        Returns the response text or None on failure.
        """
        if not self.is_available():
            logger.debug("LLM not available, skipping")
            return None

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            if self._provider == LLMProvider.MINIMAX:
                return self._call_minimax(messages, max_tokens, temperature)
            elif self._provider == LLMProvider.MINIMAX_CLI:
                return self._call_minimax_cli(messages, max_tokens, temperature)
            elif self._provider == LLMProvider.OPENAI:
                return self._call_openai(messages, max_tokens, temperature)
            else:
                return self._call_ollama(messages, max_tokens, temperature)
        except Exception as e:
            logger.error(f"LLM chat failed: {e}")
            return None

    def complete(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> Optional[str]:
        """
        Simple prompt completion (used by ImageMatcher).
        Delegates to chat() with a single user message.
        """
        return self.chat(prompt=prompt, max_tokens=max_tokens, temperature=temperature)

    def _call_minimax(
        self, messages: List[Dict], max_tokens: int, temperature: float
    ) -> Optional[str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(
            self._api_url, headers=headers, json=payload, timeout=60
        )
        logger.info(f"MiniMax API response status: {resp.status_code}")
        logger.info(f"MiniMax API response body: {resp.text[:500]}")
        if resp.status_code == 200:
            data = resp.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            # MiniMax puts content in reasoning_content for reasoning models
            return msg.get("content") or msg.get("reasoning_content") or ""
        logger.error(f"MiniMax error {resp.status_code}: {resp.text[:200]}")
        return None

    def _call_openai(
        self, messages: List[Dict], max_tokens: int, temperature: float
    ) -> Optional[str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(
            self._api_url, headers=headers, json=payload, timeout=60
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content")
        logger.error(f"OpenAI error {resp.status_code}: {resp.text[:200]}")
        return None

    def _call_ollama(
        self, messages: List[Dict], max_tokens: int, temperature: float
    ) -> Optional[str]:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        resp = requests.post(self._api_url, json=payload, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("message", {}).get("content")
        logger.error(f"Ollama error {resp.status_code}: {resp.text[:200]}")
        return None

    def _call_minimax_cli(
        self, messages: List[Dict], max_tokens: int, temperature: float
    ) -> Optional[str]:
        """Call MiniMax via mmx CLI subprocess (for Token Plan keys that don't work with direct API)."""
        # Extract system prompt (pass separately via --system)
        system_prompt = None
        mmx_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                system_prompt = msg["content"]
            else:
                mmx_messages.append({"role": role, "content": msg["content"]})

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(mmx_messages, f, ensure_ascii=False)
            tmp_path = f.name

        try:
            cmd = [
                MMX_CLI, "text", "chat",
                "--messages-file", tmp_path,
                "--max-tokens", str(max_tokens),
                "--output", "json",
            ]
            if system_prompt:
                cmd.extend(["--system", system_prompt])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            logger.info(f"mmx CLI returncode: {result.returncode}")
            logger.info(f"mmx CLI stdout: {result.stdout[:300]}")
            logger.info(f"mmx CLI stderr: {result.stderr[:200]}")
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    # Extract text content from response
                    content = data.get("content", [])
                    if isinstance(content, list):
                        for c in content:
                            if c.get("type") == "text":
                                return c.get("text", "")
                    elif isinstance(content, str):
                        return content
                except json.JSONDecodeError:
                    # Fallback: try to find text in stdout
                    stdout = result.stdout
                    text_start = stdout.find('"text": "')
                    if text_start >= 0:
                        text_start += 8
                        text_end = stdout.find('"', text_start)
                        return stdout[text_start:text_end]
                    return stdout.strip()
            else:
                logger.error(f"mmx CLI error: {result.stderr}")
        finally:
            os.unlink(tmp_path)
        return None

    # --- Convenience methods for layout/script tasks ---

    def get_layout_suggestion(
        self,
        description: str,
        dialogue_count: int,
        dialogue_lines: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Get a layout template suggestion from the LLM.
        Falls back to None (rule-based) if LLM unavailable.
        """
        if not self.is_available():
            return None

        dialogue_text = "\n".join(
            f"{d.get('character', '')}: {d.get('text', '')}"
            for d in dialogue_lines
        )

        system_prompt = (
            "You are an expert manga layout artist. "
            "Given a scene description and dialogue, choose the best panel layout template. "
            "Always respond in valid JSON: {\"template\": \"template_name\"}. "
            "Available templates: full_bleed, half_vertical, thirds, grid_4, manga_classic, "
            "dynamic_diagonal, splash, grid_6."
        )

        user_prompt = (
            f"Scene description:\n{description[:300]}\n\n"
            f"Dialogue count: {dialogue_count}\n"
            f"Dialogue:\n{dialogue_text[:300]}"
        )

        response = self.chat(user_prompt, system=system_prompt, max_tokens=500, temperature=0.2)
        if response:
            return self._parse_template(response)
        return None

    def analyze_scene_for_layout(
        self,
        scene_description: str,
        dialogue_lines: List[Dict[str, Any]],
        image_count: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Ask LLM to analyze a scene and return structured layout advice.
        Returns a dict with keys: panel_count, layout_template, special_notes.
        """
        if not self.is_available():
            return None

        dialogue_text = "\n".join(
            f"{d.get('character', '')}: {d.get('text', '')}" for d in dialogue_lines
        )

        system_prompt = (
            "You are a professional manga storyboard artist. "
            "Analyze scenes and provide layout decisions. "
            "Always respond in valid JSON with this exact structure:\n"
            '{"panel_count": int, "layout_template": str, "emotional_tone": str, '
            '"pacing": str, "special_notes": str, "suggested_shot": str}\n'
            "panel_count: how many panels (1-6)\n"
            "layout_template: one of full_bleed, half_vertical, thirds, grid_4, manga_classic, dynamic_diagonal, splash, grid_6\n"
            "emotional_tone: intense/calm/romantic/comedic/mysterious/surprised\n"
            "pacing: fast/slow/medium\n"
            "special_notes: any composition advice (e.g. 'use bleeds for impact')\n"
            "suggested_shot: close_up/wide_shot/medium_shot/POV/over_shoulder/diagonal\n"
        )

        user_prompt = (
            f"Scene:\n{scene_description[:400]}\n\n"
            f"Dialogue ({len(dialogue_lines)}):\n{dialogue_text[:300]}\n\n"
            f"Available images: {image_count}"
        )

        response = self.chat(
            user_prompt,
            system=system_prompt,
            max_tokens=2048,
            temperature=0.3,
        )
        if response:
            try:
                # Try to extract JSON from response
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    return json.loads(response[json_start:json_end])
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse LLM JSON response: {response[:100]}")
        return None

    def _parse_template(self, response: str) -> Optional[str]:
        """Extract template name from LLM text response (supports both plain text and JSON)."""
        valid = {
            'full_bleed', 'half_vertical', 'thirds', 'grid_4',
            'manga_classic', 'dynamic_diagonal', 'splash', 'grid_6',
        }
        # Try JSON first
        try:
            # Find JSON object in response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                obj = json.loads(response[json_start:json_end])
                if isinstance(obj, dict):
                    template = obj.get('template') or obj.get('layout_template') or obj.get('name')
                    if template and template in valid:
                        return template
        except json.JSONDecodeError:
            pass
        # Fallback: text search
        resp = response.lower().strip()
        for t in valid:
            if t in resp:
                return t
        return None


# --- Module-level singleton ---
_client: Optional[LLMClient] = None


def get_client() -> LLMClient:
    """Get or create the global LLM client."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def set_client(client: LLMClient) -> None:
    """Set the global LLM client (for testing/custom configs)."""
    global _client
    _client = client


def reset_client() -> None:
    """Reset the global client."""
    global _client
    _client = None
