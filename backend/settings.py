import os


class Settings:
    # Default LLM endpoint — OpenRouter's public API
    DEFAULT_LLM_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self):
        self._network_enabled = True
        self._openrouter_url = self.DEFAULT_LLM_BASE_URL
        self._emulator_url = os.environ.get(
            "EMULATOR_URL", os.environ.get("LLM_BASE_URL", "http://emulator:8000/api/v1")
        ).rstrip("/")
        # Start with whatever LLM_BASE_URL says, or default to OpenRouter
        initial = os.environ.get("LLM_BASE_URL", self.DEFAULT_LLM_BASE_URL).rstrip("/")
        self._llm_base_url = initial

    def get_network_enabled(self) -> bool:
        return self._network_enabled

    def set_network_enabled(self, enabled: bool):
        self._network_enabled = enabled

    def get_llm_base_url(self) -> str:
        """Returns the base URL for the LLM API (e.g. 'https://openrouter.ai/api/v1')."""
        return self._llm_base_url

    def set_llm_base_url(self, url: str):
        """Switch the active LLM endpoint at runtime."""
        self._llm_base_url = url.rstrip("/")

    def get_emulator_url(self) -> str:
        """Returns the emulator API URL."""
        return self._emulator_url

    def get_openrouter_url(self) -> str:
        """Returns the OpenRouter API URL."""
        return self._openrouter_url

    def is_internal_llm(self) -> bool:
        """Returns True if pointing at an internal emulator instead of OpenRouter."""
        return "openrouter.ai" not in self._llm_base_url

    def get_active_provider(self) -> str:
        """Returns 'emulator' or 'openrouter' based on current LLM URL."""
        return "openrouter" if "openrouter.ai" in self._llm_base_url else "emulator"


settings = Settings()
