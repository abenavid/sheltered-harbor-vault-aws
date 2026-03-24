#!/usr/bin/env python3
"""
Emit JSON for Ansible vault_dotenv: either parse ENV_FILE (local / AAP file injector)
or, if that path is missing, read the same keys from the environment (AAP env injector).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

# Keys used by this repo’s .env and optional AAP credentials (add here if you extend .env)
ALLOWED_KEYS = (
    "AAP_CONTROLLER_URL",
    "AAP_ADMIN_USERNAME",
    "AAP_ADMIN_PASSWORD",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_DEFAULT_REGION",
    "AWS_CONSOLE_URL",
    "AWS_CONSOLE_USER",
    "AWS_CONSOLE_PASSWORD",
    "BASTION_SSH_COMMAND",
    "BASTION_SSH_USER",
    "BASTION_SSH_HOST",
    "BASTION_SSH_PORT",
    "BASTION_SSH_PASSWORD",
    "BASTION_SSH_PUBLIC_KEY",
    "OPENSHIFT_CONSOLE_URL",
    "OPENSHIFT_KUBEADMIN_USERNAME",
    "OPENSHIFT_KUBEADMIN_PASSWORD",
    "OPENSHIFT_API_URL",
    "OPENSHIFT_BEARER_TOKEN",
    "OC_CLIENT_DOWNLOAD_URL",
)


def parse_dotenv(path: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        out[key] = value
    return out


def main() -> int:
    raw = os.environ.get("ENV_FILE", "").strip()
    if not raw:
        print("ENV_FILE is not set", file=sys.stderr)
        return 2

    path = pathlib.Path(raw)
    if path.is_file():
        data = parse_dotenv(path)
    else:
        data = {k: os.environ[k] for k in ALLOWED_KEYS if os.environ.get(k, "").strip()}

    print(json.dumps(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
