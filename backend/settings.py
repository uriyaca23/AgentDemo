import os

class Settings:
    network_enabled: bool = True
    
    @classmethod
    def get_network_enabled(cls):
        return cls.network_enabled
    
    @classmethod
    def set_network_enabled(cls, enabled: bool):
        cls.network_enabled = enabled

settings = Settings()
