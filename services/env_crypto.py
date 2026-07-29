from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


ENC_PREFIX = "ENC["
ENC_SUFFIX = "]"


def is_encrypted_env_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(ENC_PREFIX)
        and value.endswith(ENC_SUFFIX)
    )


def decrypt_env_value(value: object, secret_key: str | None) -> object:
    if not is_encrypted_env_value(value):
        return value
    if not secret_key:
        raise ValueError("ENV_SECRET_KEY is required for encrypted .env values")

    encrypted_value = str(value)[len(ENC_PREFIX) : -len(ENC_SUFFIX)]
    try:
        return Fernet(secret_key.encode("utf-8")).decrypt(
            encrypted_value.encode("utf-8")
        ).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Cannot decrypt encrypted .env value") from exc
