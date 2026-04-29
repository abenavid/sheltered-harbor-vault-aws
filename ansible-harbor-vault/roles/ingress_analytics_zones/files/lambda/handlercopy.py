import boto3
import os

# S3Control is used for Batch Operations
s3_control = boto3.client('s3control')

# Configuration parameters
ACCOUNT_ID = os.environ("AWS_ACCOUNT_ID")  # Your AWS Account ID
COPY_ROLE_ARN = os.environ("COPY_ROLE_ARN")
DEST_BUCKET_ARN = os.environ("DEST_BUCKET_ARN")
SOURCE_BUCKET_ARN = os.environ("SOURCE_BUCKET_ARN")

def create_s3_batch_copy_job():
    response = s3_control.create_job(
        AccountId=ACCOUNT_ID,
        ConfirmationRequired=False,
        Operation={
            'S3PutObjectCopy': {
                'TargetResource': DEST_BUCKET_ARN,
                'StorageClass': 'STANDARD',
                'MetadataDirective': 'COPY'
            }
        },
        ManifestGenerator={
            'EnableManifestOutput': False,
            'SourceBucket': SOURCE_BUCKET_ARN
#             'ExpectedBucketOwner': '',
#             'Filter': '',
#             'ManifestOutputLocation': ''
        },
        Report={
#             'Bucket': 'arn:aws:s3:::job-reports-bucket',
#             'Format': 'Report_CSV_20180820',
            'Enabled': False
#             'Prefix': 'batch-copy-reports',
#             'ReportScope': 'AllTasks'
        },
        Priority=10,
        RoleArn=COPY_ROLE_ARN
    )
    return response['JobId']

job_id = create_s3_batch_copy_job()
print(f"Created Batch Job ID: {job_id}")

