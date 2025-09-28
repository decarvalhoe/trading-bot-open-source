"""Utilities to encrypt and decrypt local .env files."""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

DEFAULT_PASSPHRASE_ENV = "LOCAL_ENV_PASSPHRASE"
DEFAULT_SALT_LENGTH = 16


class EnvCryptoError(RuntimeError):
    """Raised when encryption or decryption fails."""


def _derive_key(passphrase: str, *, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _encrypt(raw: bytes, passphrase: str) -> dict[str, str]:
    salt = secrets.token_bytes(DEFAULT_SALT_LENGTH)
    key = _derive_key(passphrase, salt=salt)
    cipher = Fernet(key)
    token = cipher.encrypt(raw)
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "ciphertext": base64.b64encode(token).decode("ascii"),
        "version": 1,
    }


def _decrypt(payload: dict[str, Any], passphrase: str) -> bytes:
    try:
        salt = base64.b64decode(payload["salt"])
        ciphertext = base64.b64decode(payload["ciphertext"])
    except Exception as exc:  # pragma: no cover - defensive guard
        raise EnvCryptoError("Encrypted payload is corrupted") from exc
    key = _derive_key(passphrase, salt=salt)
    cipher = Fernet(key)
    return cipher.decrypt(ciphertext)


def _resolve_passphrase(value: str | None, *, env_var: str) -> str:
    if value:
        return value
    env_value = os.getenv(env_var)
    if env_value:
        return env_value
    raise EnvCryptoError(
        f"Passphrase is required. Provide --passphrase or set the {env_var} environment variable."
    )


def _load_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise EnvCryptoError(f"Encrypted file '{path}' not found") from exc


def cmd_encrypt(args: argparse.Namespace) -> None:
    passphrase = _resolve_passphrase(args.passphrase, env_var=args.passphrase_env)
    source = Path(args.input)
    if not source.exists():
        raise EnvCryptoError(f"Input file '{source}' not found")
    payload = _encrypt(source.read_bytes(), passphrase)
    Path(args.output).write_text(json.dumps(payload, indent=2))


def cmd_decrypt(args: argparse.Namespace) -> None:
    passphrase = _resolve_passphrase(args.passphrase, env_var=args.passphrase_env)
    payload = _load_file(Path(args.input))
    raw = _decrypt(payload, passphrase)
    output_path = Path(args.output)
    output_path.write_bytes(raw)
    if args.print_env:
        print(raw.decode("utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Encrypt or decrypt local environment files")
    parser.set_defaults(func=None)

    sub = parser.add_subparsers(dest="command")

    encrypt_parser = sub.add_parser("encrypt", help="Encrypt a plain-text .env file")
    encrypt_parser.add_argument("--input", default=".env", help="Path to the plain-text file to encrypt")
    encrypt_parser.add_argument(
        "--output",
        default=".env.enc",
        help="Path where the encrypted payload should be written",
    )
    encrypt_parser.add_argument("--passphrase", help="Passphrase used to derive the encryption key")
    encrypt_parser.add_argument(
        "--passphrase-env",
        default=DEFAULT_PASSPHRASE_ENV,
        help="Environment variable containing the passphrase",
    )
    encrypt_parser.set_defaults(func=cmd_encrypt)

    decrypt_parser = sub.add_parser("decrypt", help="Decrypt an encrypted .env payload")
    decrypt_parser.add_argument("--input", default=".env.enc", help="Encrypted payload to decrypt")
    decrypt_parser.add_argument(
        "--output",
        default=".env.runtime",
        help="Location where the decrypted file should be written",
    )
    decrypt_parser.add_argument("--passphrase", help="Passphrase used to derive the encryption key")
    decrypt_parser.add_argument(
        "--passphrase-env",
        default=DEFAULT_PASSPHRASE_ENV,
        help="Environment variable containing the passphrase",
    )
    decrypt_parser.add_argument(
        "--print-env",
        action="store_true",
        help="Echo the decrypted content to stdout (useful for piping into other tools)",
    )
    decrypt_parser.set_defaults(func=cmd_decrypt)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return
    try:
        args.func(args)
    except EnvCryptoError as exc:  # pragma: no cover - CLI guard
        parser.error(str(exc))


if __name__ == "__main__":  # pragma: no cover - CLI entry-point
    main()
