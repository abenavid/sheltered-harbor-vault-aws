import boto3

def lambda_handler(event, context):
    s3_control = boto3.client('s3control')
    account_id = os.environ["AWS_ACCOUNT_ID"]
    copy_role_arn = os.environ["COPY_ROLE_ARN"]

    response = s3_control.create_job(
        AccountId=account_id,
        ConfirmationRequired=False,
        Operation={
            'LambdaInvoke': {
                'FunctionArn': 'arn:aws:lambda:region:account-id:function:process-object'
            }
        },
        Manifest={
            'Spec': {'Format': 'S3BatchOperations_CSV_20180820'},
            'Location': {
                'ObjectArn': 'arn:aws:s3:::my-bucket/manifest.csv',
                'ETag': 'manifest-file-etag'
            }
        },
        Report={
            'Bucket': 'arn:aws:s3:::my-report-bucket',
            'Format': 'Report_CSV_20180820',
            'Enabled': True,
            'Prefix': 'batch-reports',
            'ReportScope': 'AllTasks'
        },
        Priority=10,
        RoleArn=copy_role_arn
    )
    return response

