class Settings:
    def __init__(self):
        self._network_enabled = True

    def get_network_enabled(self) -> bool:
        return self._network_enabled

    def set_network_enabled(self, enabled: bool):
        self._network_enabled = enabled

settings = Settings()
