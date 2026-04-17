# Sheltered Harbor–style AWS data vault (Ansible)

This repository automates a minimal **Sheltered Harbor–aligned data vault** on AWS using native services: a **customer-managed KMS key**, an **S3 bucket** with **Object Lock** (WORM) and **SSE-KMS**, and an **IAM role** scoped for vault writes. The design intent matches the [AWS Sheltered Harbor Validated Vaulting Architecture](https://shelteredharbor.org/aws-sheltered-harbor-vaulting-architecture) article: an encrypted, **immutable** store that is **logically separated** from normal operations, with **least-privilege** access for writers.

The article frames three themes—**secure and immutable vault**, **air-gapped / isolated environment**, and **forensic scanning**—mapped below to what this codebase does and does not provision.

![AWS architecture diagram: secure data pipeline with Ingress, Analytics, Vault, Forensics, and Egress zones; data flows from ingestion to recovery via Direct Connect; Management Interface zone; shared services IAM, KMS, CloudWatch, CloudTrail, Macie, GuardDuty, and SNS.](docs/assets/sheltered-harbor-vault-architecture.png)


## How this maps to the reference architecture

### Secure and immutable data vault

| Article concept                   | What this repo does                                                                                                                                                                                                              |
|-----------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Immutable storage / WORM (Object Lock) | The `backup_vault` role creates a logically air-gapped versioned bucket with Object Lock **COMPLIANCE** mode and a default retention period (`min_retention_days` and `max_retention_days` in `backup_vault/defaults/main.yml`). |
| Encryption at rest (e.g. SSE-KMS) | The logically air-gapped vault uses **SSE-KMS** with the CMK created by the `kms` role (`encryption: aws:kms`, `encryption_key_id` from the key ARN).                                                                            |
| KMS for key control               | The `kms` role provisions a **customer-managed** key (`kms_alias`, default `alias/sheltered-harbor-vault`).                                                                                                                      |
| **TODO: Not Used** Security of the vault (IAM boundaries) | The `iam_writer` role defines **VaultWriteRole** + **VaultWritePolicy**: `s3:PutObject` / `s3:PutObjectRetention` on the vault bucket prefix and `kms:Encrypt` / `kms:GenerateDataKey` on that CMK only.                         |

**TODO: Not Used but how does backup service handle this** **Encryption in transit:** The `s3_vault` role attaches a bucket policy that **denies all S3 actions** when `aws:SecureTransport` is false (requests not over HTTPS/TLS).

### Air-gapped (isolated) environment

**TODO: Replace with information on how AWS Backup service logically air-gapped vaults and backup plans accomplish this same thing**
The article describes **separate AWS Organizations**, **cross-account IAM**, **Direct Connect**, **Lambda/EventBridge** for time-bound access, and network controls. The vault account side still centers on **VaultWriteRole** and the **cross-account–capable writer** trust.

- **VaultWriteRole** trusts `arn:aws:iam::<trusted_account_id>:root` when `trusted_account_id` is set in `inventories/group_vars/all.yml`. If you omit it or leave the placeholder `111111111111`, the playbook defaults the trust to the **same account** as the caller (`bootstrap_vault.yml` resolves `trusted_account_id` from `amazon.aws.aws_caller_info`).
- **Optional automation** (`playbooks/bootstrap_network_isolation.yml`): **Organizations** OU + example SCP (CloudFormation in the **organization management account** when `vault_org_parent_id` is set); **VPC** with public, **ingress**, and **egress** subnets, NAT for the egress zone, S3 gateway and KMS/STS interface endpoints, and a **virtual private gateway** for Direct Connect/VPN paths; **Direct Connect gateway** association with that VGW (`community.aws.directconnect_gateway` when `vault_direct_connect_enabled`); **EventBridge schedules** invoking a **Lambda** that attaches or detaches the managed policy `VaultWriteManagedPolicy` on `VaultWriteRole` when `vault_time_bound_access` is true (run `bootstrap_vault.yml` first so the policy and role exist). Physical Direct Connect circuits, private VIF workflow, Transit Gateway, and full “pull into vault” data paths remain **your** design and AWS provisioning outside these playbooks.
- **Writer policy shape:** `iam_writer` now creates a **customer-managed policy** `VaultWriteManagedPolicy` (replacing the previous inline `VaultWritePolicy`) so time-bound mode can attach/detach the same policy document.

### Forensic scanning of data

Amazon GuardDuty Malware Protection can be used with AWS Backup. You can automatically scan your backups for malware. 
This integration helps you detect malicious code in your backups and identify clean recovery points for restore operations.
Amazon GuardDuty Malware Protection supports two primary workflows for scanning your backups:

- **Automatic malware scanning through backup plans:** Enable malware scanning in backup plans to automate malware detection with AWS Backup. 
When enabled, AWS Backup automatically initiates an Amazon GuardDuty scan after each successful backup completion. 
You can configure either full or incremental scanning for specific backup plan rules, which determines how frequently your backups are scanned. 
For more information about scan types, see [Incremental vs full scans](https://docs.aws.amazon.com/aws-backup/latest/devguide/malware-protection.html#malware-scan-types). 
AWS Backup recommends enabling automatic malware scanning in backup plans for proactive threat detection after backup creation.

- **On-demand scans:** Run on-demand scans to manually scan existing backups, choosing between full or incremental scan types. 
AWS Backup recommends using on-demand scans to identify your last clean backup. When scanning before a restore operation, 
use a full scan to examine the entire backup with the latest threat detection model.

In the `backup_plan` role the Jinja2 template `roles/backup_plan/files/backup_plan.j2` shows an example of the `ScanSettings` section
where configuration can be added for GuardDuty malware scanning.

### Operational assurance (logging and monitoring)
**TODO: Not Used**
The article references **CloudTrail**, **GuardDuty**, and monitoring KMS usage. When `vault_logging_monitoring_enabled` is true, the `logging_monitoring` role provisions a **multi-region CloudTrail** (dedicated S3 bucket, log file validation), optionally **CloudWatch Logs** delivery when `vault_cloudtrail_cloudwatch_logs_enabled` is true, enables the regional **GuardDuty detector**, creates an **SNS topic** for security notifications (unless you set `vault_security_alarm_sns_topic_arn` to an existing topic), optionally a **CloudWatch metric filter** on the trail log group for critical **KMS APIs** against the vault CMK (`DisableKey`, `ScheduleKeyDeletion`, `DeleteAlias`) with an alarm to SNS, and an **EventBridge rule** that forwards **GuardDuty findings** at or above `vault_guardduty_alarm_min_severity` to that topic. **Creating** a trail with CloudWatch Logs requires the **deploying IAM principal** to have **`iam:PassRole`** on the CloudTrail→CloudWatch Logs role for `cloudtrail.amazonaws.com`; otherwise `CreateTrail` can fail with `InvalidCloudWatchLogsRoleArnException` (often phrased as a trust issue). Grant PassRole on `arn:aws:iam::<account>:role/<vault_cloudtrail_cw_role_name>` (default `CloudTrailCloudWatchLogsRole`), or set `vault_cloudtrail_cloudwatch_logs_enabled: false` to skip CWL and the KMS log-based alarm until PassRole is in place. If you supply your own SNS topic ARN, attach a policy that allows **CloudWatch** and **EventBridge** to publish (see the role’s SNS policy for the `vault-*` rule prefix). Organization-level trails, delegated admin, and subscriber endpoints (email, ticketing) are still yours to configure.

---

## Repository layout

All automation lives under **`ansible-harbor-vault/`**:

| Path                                                             | Role                                                                                                                                                                                                                                                                                                                                                                      |
|------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ansible-harbor-vault/playbooks/bootstrap_vault.yml`             | Entry playbook: loads `.env` for AWS credentials/region, resolves caller account and optional `trusted_account_id`, then runs `kms` → `s3_vault` → optional `forensic_scanning` → `iam_writer` → optional `logging_monitoring`.                                                                                                                                           |
| `ansible-harbor-vault/playbooks/bootstrap_backup_vault.yml`      | Backup vault playbook: resolves AWS credentials, sets AWS region, resolves caller account and optional `trusted_account_id`, then runs `kms` → `backup_vault` roles to create logically air-gapped vault using AWS Backup service.                                                                                                                                        |
| `ansible-harbor-vault/playbooks/bootstrap_backup_plan.yml`       | Backup plan playbook: resolves AWS credentials, sets AWS region, resolves caller account and optional `trusted_account_id`, then runs `kms` → `backup_plan` roles to create AWS Backup service backup plan for logically air-gapped vault created by the `backup_vault` role. The backup plan defines backup policies, GuardDuty scanning and backup resource assignment. |
| `ansible-harbor-vault/playbooks/bootstrap_network_isolation.yml` | Optional: Organizations OU/SCP, VPC zones and endpoints, Direct Connect gateway association, Lambda/EventBridge time-bound writer policy (see `inventories/group_vars/all.yml`).                                                                                                                                                                                          |
| `ansible-harbor-vault/inventories/localhost.yml`                 | Single local host for `connection: local` runs.                                                                                                                                                                                                                                                                                                                           |
| `ansible-harbor-vault/inventories/group_vars/all.yml`            | Defaults: `aws_region`, `vault_bucket_name`, `vault_retention_years`, `kms_alias`, optional `trusted_account_id`; flags such as `vault_forensic_scanning_enabled`, `vault_logging_monitoring_enabled`.                                                                                                                                                                    |
| `ansible-harbor-vault/roles/aws_api_credentials/`                | Creates the required security tokens for signing HTTP requests to AWS services apis.                                                                                                                                                                                                                                                                                      |
| `ansible-harbor-vault/roles/backup_plan/`                        | Creates AWS Backup service backup plan for a logically air-gapped vault. The backup plan defines backup policies, GuardDuty scanning and backup resource assignment.                                                                                                                                                                                                      |
| `ansible-harbor-vault/roles/backup_vault/`                       | Creates a logically air-gapped vault using the AWS Backup service. Requests to the AWS Backup service api are signed using security tokens obtained from `aws_api_credentials` role.                                                                                                                                                                                      |
| `ansible-harbor-vault/roles/kms/`                                | Creates the **CMK** used by the bucket and writer policy.                                                                                                                                                                                                                                                                                                                 |
| `ansible-harbor-vault/roles/s3_vault/`                           | Creates the **S3 bucket**: versioning, Object Lock, block public access, SSE-KMS.                                                                                                                                                                                                                                                                                         |
| `ansible-harbor-vault/roles/iam_writer/`                         | Creates **VaultWriteRole** and customer-managed **VaultWriteManagedPolicy** for least-privilege writes.                                                                                                                                                                                                                                                                   |
| `ansible-harbor-vault/roles/forensic_scanning/`                  | Optional: GuardDuty Malware Protection for S3, EventBridge→SNS, partner scanner role.                                                                                                                                                                                                                                                                                     |
| `ansible-harbor-vault/roles/logging_monitoring/`                 | Optional: CloudTrail (S3 + CloudWatch Logs), GuardDuty detector, KMS metric filter + alarm, GuardDuty→SNS via EventBridge.                                                                                                                                                                                                                                                |
| `ansible-harbor-vault/roles/network_isolation/`                  | Optional VPC, ingress/egress subnets, NAT, endpoints, VGW (when enabled).                                                                                                                                                                                                                                                                                                 |
| `ansible-harbor-vault/roles/direct_connect_gateway/`             | Optional Direct Connect gateway + VGW association.                                                                                                                                                                                                                                                                                                                        |
| `ansible-harbor-vault/roles/org_isolation/`                      | Optional Organizations OU + example SCP (management account).                                                                                                                                                                                                                                                                                                             |
| `ansible-harbor-vault/roles/time_bound_access/`                  | Optional Lambda + EventBridge schedules to attach/detach **VaultWriteManagedPolicy**.                                                                                                                                                                                                                                                                                     |
| `ansible-harbor-vault/requirements.yml`                          | Same collection pins as `collections/requirements.yml` (for local runs from `ansible-harbor-vault/`).                                                                                                                                                                                                                                                                     |
| `collections/requirements.yml`                                   | **AWX/AAP**: `amazon.aws` (>= 8.2.0), `community.aws` (>= 8.0.0). Controller installs this when the project root is the repository root.                                                                                                                                                                                                                                  |
| `ansible-harbor-vault/requirements-python.txt`                   | Optional EE hint: **boto3>=1.42.54** for GuardDuty malware protection plan APIs.                                                                                                                                                                                                                                                                                          |
| `ansible-harbor-vault/ansible.cfg`                               | Sets inventory path and `roles_path`.                                                                                                                                                                                                                                                                                                                                     |
| `execution-environment.yml`                                      | **Ansible Builder 3** definition: AAP 26 **ee-supported-rhel9** base, `collections/requirements.yml`, **ansible-core** / **ansible-runner**, **boto3** via `requirements-python.txt`, `ee/bindep.txt` (e.g. **python3-pip** for the builder stage). Adjust this file as you iterate.                                                                                      |
| `ee/bindep.txt`                                                  | System packages for the EE build (bindep format); referenced from `execution-environment.yml`.                                                                                                                                                                                                                                                                            |
| `Containerfile`                                                  | **Thin alternative**: same base image, only upgrades **boto3>=1.42.54** (fast, reliable push to PAH when builder hits unrelated collection pip builds on ee-supported).                                                                                                                                                                                                   |

---

## Using AWS Backup Service As Sheltered Harbor Compliant Solution

Organizations subject to the Sheltered Harbor standard require their data vaults to maintain immutability, provide isolation from production infrastructure, 
and enable forensic validation of backup data integrity. AWS Backup logically air-gapped vault addresses these fundamental requirements through three key capabilities: 
it maintains backup immutability using a compliance mode lock, provides isolation from production infrastructure through logical air-gapping, 
and enables forensic validation of backup data integrity through seamless integration with AWS Backup restore testing.

The following sections detail playbooks/roles used to leverage the AWS Backup service to implement the `Sheltered Harbor` standard.

### Signing Requests to AWS Services

Authentication information that you send in a AWS API request must include a signature. 
AWS Signature Version 4 (SigV4) is the AWS signing protocol for adding authentication information to AWS API requests.
You don't use your secret access key to sign API requests. Instead, you use the SigV4 signing process. Signing requests involves:

- Creating a canonical request based on the request details.

- Calculating a signature using your AWS credentials.

- Adding this signature to the request as an `Authorization` header.

AWS then replicates this process and verifies the signature, granting or denying access accordingly.

For more information see [AWS Signature Version 4 for API requests](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv.html)

The `aws_api_credentials` role calculates the signature for the Authorization header using the rules defined here,
[Signature Calculations for the Authorization Header: Transferring Payload in a Single Chunk (AWS Signature Version 4)](https://docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-header-based-auth.html)

The following details the tasks performed by the `aws_api_credentials` role.

First temporary credentials are obtained using the `get-session-token` operation of the `sts` service. These credentials are then 
used to populate the `aws_api_session_token` , `aws_api_access_key_id` and `aws_api_secret_access_key` facts.

```yaml
      - name: Get Temp Session Token
        ansible.builtin.command: >
          aws sts get-session-token --duration-seconds 3600
        register: session_token_response
        delegate_to: localhost

      - name: Set Session Token Info variable
        ansible.builtin.set_fact:
          session_token_info: "{{ session_token_response.stdout | from_json }}"

      - name: Set facts for temp session token, access key id and secret access key
        ansible.builtin.set_fact:
          aws_api_session_token: "{{ session_token_info.Credentials.SessionToken }}"
          aws_api_access_key_id: "{{ session_token_info.Credentials.AccessKeyId }}"
          aws_api_secret_access_key: "{{ session_token_info.Credentials.SecretAccessKey }}"
        no_log: true
```

A `jinja2` template was created in `files/auth.py.j2` that will generate a Python script file that will be used to calculate 
the required headers for signing the AWS API request. See the `files/auth.py.j2` template contents and the reference above to see
how these headers are calculated. The following shows only the parts of the script that are dynamic requiring input values 
from the caller generating the script.

The following environment variables must be set to the values of the temporary credentials created by the `sts` service.

````
# AWS access keys
access_key = os.environ['AWS_ACCESS_KEY_ID']
secret_key = os.environ['AWS_SECRET_ACCESS_KEY']
session_token = os.environ['AWS_SESSION_TOKEN']
````

The ansible role or playbook that is using the `aws_api_credentials` role must define the following facts for the service and 
api endpoint being requested.

````
# Request parameters
method = "{{ api_http_method }}"
service = '{{ api_service }}'
host = "{{ api_host }}"
region = "{{ aws_region }}"
endpoint = "{{ api_endpoint }}"
````

The payload of the request body must be set as a fact called `request_payload`. It is used in the following line in the script.
If the request body is empty just set the `request_payload` fact to an empty string.

````
payload_hash = hashlib.sha256('{{ request_payload }}'.encode('utf-8')).hexdigest()
````

The script returns the following header values in JSON format.

````
# Make the headers
headers = {"x_amz_date": amzdate,
           "x_amz_security_token": session_token,
           "Authorization": authorization_header}
print(json.dumps(headers))
````

The Python `auth.py` is executed with the following environment settings.

```yaml
environment:
  AWS_SESSION_TOKEN: "{{ aws_api_session_token }}"
  AWS_ACCESS_KEY_ID: "{{ aws_api_access_key_id }}"
  AWS_SECRET_ACCESS_KEY: "{{ aws_api_secret_access_key }}"
```

After executing the script, the `aws_api_credentials` role parses this JSON to extract values to populate the 
`x_amz_date`, `x_amz_security_token` and `Authorizaton` facts.

The ansible role or playbook that is using the `aws_api_credentials` role then uses these facts to populate the 
`x-amz-date`, `x-amz-security-token` and `Authorizaton` request headers when making the request to the AWS API.

### Creating Logically Air-gapped Vault

The `backup_vault` role was created o create a logically air-gapped vault in the AWS Backup service. The following details
the tasks in the `backup_vault` role.

To create the logically air-gapped vault, a request is made to the AWS Backup service API. The documentation for the 
AWS Backup service API can be found here, [AWS Backup API](https://docs.aws.amazon.com/aws-backup/latest/devguide/api-reference.html)
The documentation for the action that creates the logically air-gapped vault can be found here, [CreateLogicallyAirGappedBackupVault](https://docs.aws.amazon.com/aws-backup/latest/devguide/API_CreateLogicallyAirGappedBackupVault.html)

For requests made to AWS API, the authentication information that you send must include a signature. 
AWS Signature Version 4 (SigV4) is the AWS signing protocol for adding authentication information to AWS API requests.

For this reason, the `aws_api_credentials` roles was created as described above.

The first task forthe `backup_vault` role is to create facts required by the `aws_api_credentials` role and the `uri` module used
to make the request to the AWS Backup service API. The following are the required facts.

```yaml
      - name: Set endpoint, http method and request payload
        ansible.builtin.set_fact:
          api_http_method: "PUT"
          api_service: "backup"
          api_host: "backup.{{ aws_region }}.amazonaws.com"
          api_endpoint: "/logically-air-gapped-backup-vaults/{{ vault_name }}"
          request_payload: "{{ create_vault_request | to_json }}"
        no_log: true

````
The following describes each fact listed above.

- `api_hhtp_method`: The HTTP method required by the API endpoint.
- `api_service`: The AWS service name. For example, the AWS Backup service has the name of `backup`.
- `api_host`: The host name for the AWS service.
- `api_endpoint`: The API endpoint for the request. **Note:** The above endpoint contains a path variable `vault_name` containing the name of the vault that is created.
- `request_payload`: The API request body.

With these facts set, the next task is to call the `aws_api_credentials` role.

````yaml
      - name: Call aws_api_credentials Role to get credentials for api request
        ansible.builtin.include_role:
          name: ../roles/aws_api_credentials
````

Next the API request to create the logically air-gapped vault is made using the `uri` module.

````yaml
      - name: Create logically air-gapped Backup Vault
        ansible.builtin.uri:
          url: "{{ aws_backup_base_url }}{{ api_endpoint }}"
          method: "{{ api_http_method }}"
          headers:
            host: "{{ api_host }}"
            x-amz-date: "{{ x_amz_date }}"
            x-amz-security-token: "{{ x_amz_security_token }}"
            Authorization: "{{ Authorization }}"
          body: "{{ request_payload }}"
          force_basic_auth: false
          status_code: 200
          body_format: json
          use_proxy: false
          validate_certs: false
          return_content: true
        environment:
          AWS_SESSION_TOKEN: "{{ aws_api_session_token }}"
          AWS_ACCESS_KEY_ID: "{{ aws_api_access_key_id }}"
          AWS_SECRET_ACCESS_KEY: "{{ aws_api_secret_access_key }}"
        register: vault_creation_response
        delegate_to: localhost

````

**Note:** The values for the `x-amz-date`, `x-amz-security-token` and `Authorization` request headers are obtained from the `aws_api_credentials` role.

**Note:** The `envionment` variable values for the above task are obtained from the `aws_api_credentials` role.

Finally, the value of the `BackupVaultArn` element in the API response is extracted and used to populate the `backup_vault_urn` variable
that is made available to other jobs in the workflow using `set_stats`. Specifically, the job running the template for the `bootstrap_backup_plan.yml` playbook.

````yaml
      - name: Set vault info variable
        ansible.builtin.set_fact:
          vault_info: "{{ vault_creation_response.content | from_json }}"

      - name: Set the ARN (Amazon Resource Name) of the vault
        ansible.builtin.set_fact:
          vault_arn: "{{ vault_info.BackupVaultArn }}"

      - name: Set values to pass to workflow
        ansible.builtin.set_stats:
          data:
            backup_vault_arn: "{{ vault_arn }}"
````


### Creating Backup Plan



## Execution environment (container image)

You can build in two ways:

**1. Ansible Builder** ([ansible-builder](https://ansible.readthedocs.io/projects/builder/) 3.1+): edit **`execution-environment.yml`** and **`ee/bindep.txt`**, then from the repo root:

```bash
podman login registry.redhat.io
python3 -m venv .venv-ee && source .venv-ee/bin/activate
pip install 'ansible-builder>=3.1'
ansible-builder build -f execution-environment.yml -t sheltered-harbor-vault-ee:latest
```

**2. Containerfile** (minimal layer on the same supported base—useful if builder fails on native pip deps pulled in from other collections in the base image):

```bash
podman login registry.redhat.io
podman build -f Containerfile -t sheltered-harbor-vault-ee:latest .
```

**Private Automation Hub:** log in to your hub’s container registry hostname (for example `podman login aap-hub-aap.apps.<cluster>.dynamic.redhatworkshops.io` as a hub user with push rights), tag, and push. This environment was pushed as:

`aap-hub-aap.apps.cluster-wf7cj-1.dynamic.redhatworkshops.io/ansible/sheltered-harbor-vault-ee:latest`

Use that image URL in the controller’s **Execution Environment** (or pass the same reference to [ansible-navigator](https://ansible.readthedocs.io/projects/navigator/)). `pip` may warn about **aiobotocore** vs newer **botocore**; synchronous **boto3** use in this repo is unaffected.

With ansible-navigator from `ansible-harbor-vault/` (adjust the image to your registry):

```bash
ansible-navigator run playbooks/bootstrap_vault.yml \
  --execution-environment-image aap-hub-aap.apps.cluster-wf7cj-1.dynamic.redhatworkshops.io/ansible/sheltered-harbor-vault-ee:latest
```

---

## Prerequisites

- Ansible with [amazon.aws](https://github.com/ansible-collections/amazon.aws) and [community.aws](https://github.com/ansible-collections/community.aws) installed (see `collections/requirements.yml` at the repo root, or `ansible-harbor-vault/requirements.yml` when working only in that directory).

## Configuration

1. **Install collections**

   From the repository root (matches AWX when the project root is the whole repo):

   ```bash
   ansible-galaxy collection install -r collections/requirements.yml
   ```

   Or from `ansible-harbor-vault/`:

   ```bash
   ansible-galaxy collection install -r requirements.yml
   ```

2. **TODO: This may not be relevant if using AWS Backup service** **Edit `ansible-harbor-vault/inventories/group_vars/all.yml`**: set `vault_bucket_name`, retention, region, `kms_alias`, and optionally `trusted_account_id` for cross-account **AssumeRole** from your writer account.


---
