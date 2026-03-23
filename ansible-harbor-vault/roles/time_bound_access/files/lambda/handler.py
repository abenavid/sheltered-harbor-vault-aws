"""Attach or detach VaultWriteManagedPolicy on VaultWriteRole (EventBridge schedules)."""

from __future__ import annotations

import json
import os

import boto3


def lambda_handler(event, context):
    iam = boto3.client("iam")
    role_name = os.environ["VAULT_ROLE_NAME"]
    policy_arn = os.environ["VAULT_POLICY_ARN"]

    if isinstance(event, str):
        try:
            event = json.loads(event)
        except json.JSONDecodeError:
            event = {}

    action = (event or {}).get("action", "close")

    if action == "open":
        iam.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
    else:
        iam.detach_role_policy(RoleName=role_name, PolicyArn=policy_arn)

    return {"statusCode": 200, "body": json.dumps({"action": action})}
