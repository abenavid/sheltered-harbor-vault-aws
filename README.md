# Sheltered Harbor–style AWS data vault (Ansible)

This repository automates a minimal **Sheltered Harbor–aligned data vault** on AWS using native services: a **customer-managed KMS key**, an **S3 bucket** with **Object Lock** (WORM) and **SSE-KMS**, and an **IAM role** scoped for vault writes. The design intent matches the [AWS Sheltered Harbor Validated Vaulting Architecture](https://shelteredharbor.org/aws-sheltered-harbor-vaulting-architecture) article: an encrypted, **immutable** store that is **logically separated** from normal operations, with **least-privilege** access for writers.

The article frames three themes—**secure and immutable vault**, **air-gapped / isolated environment**, and **forensic scanning**—mapped below to what this codebase does and does not provision.

![AWS architecture diagram: secure data pipeline with Ingress, Analytics, Vault, Forensics, and Egress zones; data flows from ingestion to recovery via Direct Connect; Management Interface zone; shared services IAM, KMS, CloudWatch, CloudTrail, Macie, GuardDuty, and SNS.](docs/assets/sheltered-harbor-vault-architecture.png)

## How this maps to the reference architecture

### Secure and immutable data vault

| Article concept | What this repo does |
|-----------------|---------------------|
| Immutable storage / WORM (Object Lock) | The `s3_vault` role creates a versioned bucket with Object Lock **COMPLIANCE** mode and a default retention period (`vault_retention_years` in `inventories/group_vars/all.yml`). |
| Encryption at rest (e.g. SSE-KMS) | The bucket uses **SSE-KMS** with the CMK created by the `kms` role (`encryption: aws:kms`, `encryption_key_id` from the key ARN). |
| KMS for key control | The `kms` role provisions a **customer-managed** key (`kms_alias`, default `alias/sheltered-harbor-vault`). |
| Security of the vault (IAM boundaries) | The `iam_writer` role defines **VaultWriteRole** + **VaultWritePolicy**: `s3:PutObject` / `s3:PutObjectRetention` on the vault bucket prefix and `kms:Encrypt` / `kms:GenerateDataKey` on that CMK only. |

**Encryption in transit:** The `s3_vault` role attaches a bucket policy that **denies all S3 actions** when `aws:SecureTransport` is false (requests not over HTTPS/TLS).

### Air-gapped (isolated) environment

The article describes **separate AWS Organizations**, **cross-account IAM**, **Direct Connect**, **Lambda/EventBridge** for time-bound access, and network controls. The vault account side still centers on **VaultWriteRole** and the **cross-account–capable writer** trust.

- **VaultWriteRole** trusts `arn:aws:iam::<trusted_account_id>:root` when `trusted_account_id` is set in `inventories/group_vars/all.yml`. If you omit it or leave the placeholder `111111111111`, the playbook defaults the trust to the **same account** as the caller (`bootstrap_vault.yml` resolves `trusted_account_id` from `amazon.aws.aws_caller_info`).
- **Optional automation** (`playbooks/bootstrap_network_isolation.yml`): **Organizations** OU + example SCP (CloudFormation in the **organization management account** when `vault_org_parent_id` is set); **VPC** with public, **ingress**, and **egress** subnets, NAT for the egress zone, S3 gateway and KMS/STS interface endpoints, and a **virtual private gateway** for Direct Connect/VPN paths; **Direct Connect gateway** association with that VGW (`community.aws.directconnect_gateway` when `vault_direct_connect_enabled`); **EventBridge schedules** invoking a **Lambda** that attaches or detaches the managed policy `VaultWriteManagedPolicy` on `VaultWriteRole` when `vault_time_bound_access` is true (run `bootstrap_vault.yml` first so the policy and role exist). Physical Direct Connect circuits, private VIF workflow, Transit Gateway, and full “pull into vault” data paths remain **your** design and AWS provisioning outside these playbooks.
- **Writer policy shape:** `iam_writer` now creates a **customer-managed policy** `VaultWriteManagedPolicy` (replacing the previous inline `VaultWritePolicy`) so time-bound mode can attach/detach the same policy document.

### Forensic scanning of data

The article mentions **GuardDuty Malware Protection for S3** and partner scanners. When `vault_forensic_scanning_enabled` is true, the `forensic_scanning` role enables **Malware Protection for S3** on the vault bucket (IAM role, malware protection plan, optional EventBridge→SNS and partner read role). Third-party scanners and org-wide policy remain your responsibility. **Malware protection plan creation** calls AWS `CreateMalwareProtectionPlan`, which requires **boto3 ≥ 1.42.54**; the role runs `pip install --user 'boto3>=1.42.54'` for the playbook Python unless you set `vault_forensic_scanning_upgrade_boto3: false` (then bake `ansible-harbor-vault/requirements-python.txt` into your execution environment).

### Operational assurance (logging and monitoring)

The article references **CloudTrail**, **GuardDuty**, and monitoring KMS usage. When `vault_logging_monitoring_enabled` is true, the `logging_monitoring` role provisions a **multi-region CloudTrail** (dedicated S3 bucket, log file validation), optionally **CloudWatch Logs** delivery when `vault_cloudtrail_cloudwatch_logs_enabled` is true, enables the regional **GuardDuty detector**, creates an **SNS topic** for security notifications (unless you set `vault_security_alarm_sns_topic_arn` to an existing topic), optionally a **CloudWatch metric filter** on the trail log group for critical **KMS APIs** against the vault CMK (`DisableKey`, `ScheduleKeyDeletion`, `DeleteAlias`) with an alarm to SNS, and an **EventBridge rule** that forwards **GuardDuty findings** at or above `vault_guardduty_alarm_min_severity` to that topic. **Creating** a trail with CloudWatch Logs requires the **deploying IAM principal** to have **`iam:PassRole`** on the CloudTrail→CloudWatch Logs role for `cloudtrail.amazonaws.com`; otherwise `CreateTrail` can fail with `InvalidCloudWatchLogsRoleArnException` (often phrased as a trust issue). Grant PassRole on `arn:aws:iam::<account>:role/<vault_cloudtrail_cw_role_name>` (default `CloudTrailCloudWatchLogsRole`), or set `vault_cloudtrail_cloudwatch_logs_enabled: false` to skip CWL and the KMS log-based alarm until PassRole is in place. If you supply your own SNS topic ARN, attach a policy that allows **CloudWatch** and **EventBridge** to publish (see the role’s SNS policy for the `vault-*` rule prefix). Organization-level trails, delegated admin, and subscriber endpoints (email, ticketing) are still yours to configure.

---

## Repository layout

All automation lives under **`ansible-harbor-vault/`**:

| Path | Role |
|------|------|
| `ansible-harbor-vault/playbooks/bootstrap_vault.yml` | Entry playbook: loads `.env` for AWS credentials/region, resolves caller account and optional `trusted_account_id`, then runs `kms` → `s3_vault` → optional `forensic_scanning` → `iam_writer` → optional `logging_monitoring`. |
| `ansible-harbor-vault/playbooks/bootstrap_network_isolation.yml` | Optional: Organizations OU/SCP, VPC zones and endpoints, Direct Connect gateway association, Lambda/EventBridge time-bound writer policy (see `inventories/group_vars/all.yml`). |
| `ansible-harbor-vault/inventories/localhost.yml` | Single local host for `connection: local` runs. |
| `ansible-harbor-vault/inventories/group_vars/all.yml` | Defaults: `aws_region`, `vault_bucket_name`, `vault_retention_years`, `kms_alias`, optional `trusted_account_id`; flags such as `vault_forensic_scanning_enabled`, `vault_logging_monitoring_enabled`. |
| `ansible-harbor-vault/roles/kms/` | Creates the **CMK** used by the bucket and writer policy. |
| `ansible-harbor-vault/roles/s3_vault/` | Creates the **S3 bucket**: versioning, Object Lock, block public access, SSE-KMS. |
| `ansible-harbor-vault/roles/iam_writer/` | Creates **VaultWriteRole** and customer-managed **VaultWriteManagedPolicy** for least-privilege writes. |
| `ansible-harbor-vault/roles/forensic_scanning/` | Optional: GuardDuty Malware Protection for S3, EventBridge→SNS, partner scanner role. |
| `ansible-harbor-vault/roles/logging_monitoring/` | Optional: CloudTrail (S3 + CloudWatch Logs), GuardDuty detector, KMS metric filter + alarm, GuardDuty→SNS via EventBridge. |
| `ansible-harbor-vault/roles/network_isolation/` | Optional VPC, ingress/egress subnets, NAT, endpoints, VGW (when enabled). |
| `ansible-harbor-vault/roles/direct_connect_gateway/` | Optional Direct Connect gateway + VGW association. |
| `ansible-harbor-vault/roles/org_isolation/` | Optional Organizations OU + example SCP (management account). |
| `ansible-harbor-vault/roles/time_bound_access/` | Optional Lambda + EventBridge schedules to attach/detach **VaultWriteManagedPolicy**. |
| `ansible-harbor-vault/requirements.yml` | Ansible collection dependencies: `amazon.aws` (>= 8.2.0), `community.aws` (>= 8.0.0) for Direct Connect. |
| `ansible-harbor-vault/requirements-python.txt` | Optional EE hint: **boto3>=1.42.54** for GuardDuty malware protection plan APIs. |
| `ansible-harbor-vault/ansible.cfg` | Sets inventory path and `roles_path`. |

---

## Prerequisites

- Ansible with the [amazon.aws](https://github.com/ansible-collections/amazon.aws) collection installed (see `ansible-harbor-vault/requirements.yml`).
- AWS credentials that can create KMS keys, S3 buckets (with Object Lock), IAM roles, CloudTrail, CloudWatch Logs/alarms, SNS, EventBridge, and GuardDuty in the target account (exact permissions depend on which optional roles you enable).
- When **`vault_cloudtrail_cloudwatch_logs_enabled`** is true, the caller also needs **`iam:PassRole`** on the CloudTrail CloudWatch Logs role so CloudTrail can use that role. Example statement (replace account id and role name if you changed `vault_cloudtrail_cw_role_name`):

  ```json
  {
    "Effect": "Allow",
    "Action": "iam:PassRole",
    "Resource": "arn:aws:iam::ACCOUNT_ID:role/CloudTrailCloudWatchLogsRole",
    "Condition": {
      "StringEquals": { "iam:PassedToService": "cloudtrail.amazonaws.com" }
    }
  }
  ```
- A unique globally available S3 bucket name (`vault_bucket_name`).

## Configuration

1. **Install collections** (from `ansible-harbor-vault/`):

   ```bash
   ansible-galaxy collection install -r requirements.yml
   ```

2. **Create `ansible-harbor-vault/.env`** with at least:

   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_SESSION_TOKEN` (if using temporary credentials; optional otherwise)
   - `AWS_DEFAULT_REGION` (optional; playbook can also use `aws_region` in group_vars)

3. **Edit `ansible-harbor-vault/inventories/group_vars/all.yml`**: set `vault_bucket_name`, retention, region, `kms_alias`, and optionally `trusted_account_id` for cross-account **AssumeRole** from your writer account.

## Run

From `ansible-harbor-vault/`:

```bash
ansible-playbook playbooks/bootstrap_vault.yml
```

Optional isolation controls (after `ansible-galaxy collection install -r requirements.yml`):

```bash
ansible-playbook playbooks/bootstrap_network_isolation.yml
```

Dry run:

```bash
ansible-playbook playbooks/bootstrap_vault.yml --check
```

---
