# Extend AAP 2.6 supported EE with boto3 new enough for GuardDuty CreateMalwareProtectionPlan.
# Build: podman build -f Containerfile -t sheltered-harbor-vault-ee:latest .
FROM registry.redhat.io/ansible-automation-platform-26/ee-supported-rhel9:latest

RUN /usr/bin/python3.12 -m pip install --no-cache-dir --upgrade 'boto3>=1.42.54'
