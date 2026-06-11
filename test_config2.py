from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Union
class Settings(BaseSettings):
    stream_url: Union[int, str] = 0
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
s = Settings()
print(repr(s.stream_url), type(s.stream_url))
