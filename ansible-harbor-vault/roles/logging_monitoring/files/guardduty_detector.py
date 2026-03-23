#!/usr/bin/env python3
"""Enable Amazon GuardDuty detector in the given region (create or update)."""
import sys

import boto3


def main() -> None:
    region = sys.argv[1]
    client = boto3.client("guardduty", region_name=region)
    resp = client.list_detectors()
    ids = resp.get("DetectorIds") or []
    if ids:
        det = ids[0]
        client.update_detector(
            DetectorId=det,
            Enable=True,
            FindingPublishingFrequency="FIFTEEN_MINUTES",
        )
        print(det)
    else:
        out = client.create_detector(
            Enable=True,
            FindingPublishingFrequency="FIFTEEN_MINUTES",
        )
        print(out["DetectorId"])


if __name__ == "__main__":
    main()
