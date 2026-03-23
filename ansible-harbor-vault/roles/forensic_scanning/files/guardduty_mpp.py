#!/usr/bin/env python3
"""GuardDuty Malware Protection for S3 — boto3 only (no AWS CLI on PATH)."""
from __future__ import annotations

import argparse
import json
import sys


def _gd_keys(resp: dict) -> tuple[list, str | None]:
    plans = resp.get("MalwareProtectionPlans") or resp.get("malware_protection_plans") or []
    token = resp.get("NextToken") or resp.get("next_token")
    return plans, token


def _plan_id(entry: dict) -> str | None:
    return entry.get("MalwareProtectionPlanId") or entry.get("malware_protection_plan_id")


def _bucket_name(detail: dict) -> str | None:
    pr = detail.get("ProtectedResource") or detail.get("protected_resource") or {}
    s3 = pr.get("S3Bucket") or pr.get("s3_bucket") or {}
    return s3.get("BucketName") or s3.get("bucket_name")


def cmd_find(region: str, bucket: str) -> int:
    import boto3

    client = boto3.client("guardduty", region_name=region)
    token = None
    while True:
        kwargs = {}
        if token:
            kwargs["NextToken"] = token
        resp = client.list_malware_protection_plans(**kwargs)
        plans, token = _gd_keys(resp)
        for entry in plans:
            pid = _plan_id(entry)
            if not pid:
                continue
            detail = client.get_malware_protection_plan(MalwareProtectionPlanId=pid)
            if _bucket_name(detail) == bucket:
                print(pid)
                return 0
        if not token:
            break
    return 1


def cmd_create(region: str, role_arn: str, protected_json: str, tagging_enabled: bool) -> int:
    import boto3

    protected = json.loads(protected_json)
    status = "ENABLED" if tagging_enabled else "DISABLED"
    client = boto3.client("guardduty", region_name=region)
    client.create_malware_protection_plan(
        Role=role_arn,
        ProtectedResource=protected,
        Actions={"Tagging": {"Status": status}},
    )
    return 0


def cmd_sns_set_policy(region: str, topic_arn: str, policy_json: str) -> int:
    import boto3

    client = boto3.client("sns", region_name=region)
    client.set_topic_attributes(
        TopicArn=topic_arn,
        AttributeName="Policy",
        AttributeValue=policy_json,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("find", help="Print plan id if one exists for the bucket, else exit 1")
    sp.add_argument("region")
    sp.add_argument("bucket")

    sp = sub.add_parser("create", help="Create malware protection plan")
    sp.add_argument("region")
    sp.add_argument("role_arn")
    sp.add_argument("protected_resource_json")
    sp.add_argument(
        "tagging_enabled",
        choices=("true", "false"),
        help="Whether to enable post-scan object tagging",
    )

    sp = sub.add_parser("sns-set-policy", help="SNS SetTopicAttributes Policy")
    sp.add_argument("region")
    sp.add_argument("topic_arn")
    sp.add_argument("policy_json")

    args = p.parse_args()
    try:
        if args.cmd == "find":
            return cmd_find(args.region, args.bucket)
        if args.cmd == "create":
            return cmd_create(
                args.region,
                args.role_arn,
                args.protected_resource_json,
                args.tagging_enabled == "true",
            )
        if args.cmd == "sns-set-policy":
            return cmd_sns_set_policy(args.region, args.topic_arn, args.policy_json)
    except Exception as e:
        print(f"{e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
