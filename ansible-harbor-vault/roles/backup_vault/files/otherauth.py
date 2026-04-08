import requests
from aws_requests_auth.aws_auth import AWSRequestsAuth

# Configure credentials and target
auth = AWSRequestsAuth(
    aws_access_key='YOUR_ACCESS_KEY',
    aws_secret_access_key='YOUR_SECRET_KEY',
    aws_host='dynamodb.us-east-1.amazonaws.com',
    aws_region='us-east-1',
    aws_service='dynamodb'
)

# Make a signed request
response = requests.get('https://amazonaws.com', auth=auth)
print(response.json())
