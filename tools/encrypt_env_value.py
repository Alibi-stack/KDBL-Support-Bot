from __future__ import annotations

import argparse
import os
from getpass import getpass

from cryptography.fernet import Fernet


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Encrypt a value for .env as ENC[...]."
    )
    parser.add_argument("value", nargs="?", help="Plain value to encrypt")
    parser.add_argument(
        "--key",
        default=os.getenv("ENV_SECRET_KEY"),
        help="Fernet key. Defaults to ENV_SECRET_KEY.",
    )
    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Print a new ENV_SECRET_KEY and exit.",
    )
    args = parser.parse_args()

    if args.generate_key:
        print(Fernet.generate_key().decode("utf-8"))
        return

    if not args.key:
        raise SystemExit("Pass --key or set ENV_SECRET_KEY.")

    value = args.value if args.value is not None else getpass("Value: ")
    encrypted = Fernet(args.key.encode("utf-8")).encrypt(value.encode("utf-8"))
    print(f"ENC[{encrypted.decode('utf-8')}]")


if __name__ == "__main__":
    main()
