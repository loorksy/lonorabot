"""A phone's Expo push token, registered through the owner's signed-in session (VISION 11.4)."""

import re
from typing import Literal

from pydantic import SecretStr, field_validator

from .domain import Contract

# Expo push tokens: ``ExponentPushToken[...]`` (older SDKs print ``ExpoPushToken[...]``).
PUSH_TOKEN = re.compile(r"Expo(?:nent)?PushToken\[[A-Za-z0-9_-]{8,200}\]")
# A random id the app stores once per install; it names the device, never the owner.
DEVICE_ID = r"^[A-Za-z0-9-]{16,64}$"


class PushDeviceRegistration(Contract):
    # SecretStr: the token never appears in a repr, a log line or a validation error.
    token: SecretStr
    platform: Literal["android", "ios"]

    @field_validator("token")
    @classmethod
    def expo_token(cls, value: SecretStr) -> SecretStr:
        if not PUSH_TOKEN.fullmatch(value.get_secret_value()):
            raise ValueError("push_token_invalid")
        return value
