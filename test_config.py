import os
from backend.config import settings
print(f"stream_url: {repr(settings.stream_url)}")
print(f"type: {type(settings.stream_url)}")
