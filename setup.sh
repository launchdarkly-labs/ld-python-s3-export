#!/bin/bash

# LaunchDarkly to Databricks Integration Setup Script
# This script helps set up the AWS resources needed for the integration

set -e

echo "🚀 Setting up LaunchDarkly to Databricks Integration..."

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first: https://aws.amazon.com/cli/"
    exit 1
fi

# Check if user is logged in to AWS
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS credentials not configured. Please run 'aws configure' or 'aws sso login' first"
    exit 1
fi

echo "✅ AWS CLI is configured"

# Get user input
read -p "Enter your S3 bucket name (e.g., my-launchdarkly-experiments): " BUCKET_NAME
read -p "Enter your AWS region (default: us-east-1): " AWS_REGION
AWS_REGION=${AWS_REGION:-us-east-1}

echo "📦 Creating S3 bucket: $BUCKET_NAME"
aws s3 mb s3://$BUCKET_NAME --region $AWS_REGION

echo "🔐 Creating IAM role for Firehose..."

# Create trust policy
cat > firehose-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "firehose.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
  --role-name launchdarkly-firehose-role \
  --assume-role-policy-document file://firehose-trust-policy.json

# Create S3 access policy
cat > firehose-s3-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:AbortMultipartUpload",
        "s3:GetBucketLocation",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:ListBucketMultipartUploads",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::$BUCKET_NAME",
        "arn:aws:s3:::$BUCKET_NAME/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/aws/kinesisfirehose/*"
    }
  ]
}
EOF

# Attach policy to role
aws iam put-role-policy \
  --role-name launchdarkly-firehose-role \
  --policy-name FirehoseS3Policy \
  --policy-document file://firehose-s3-policy.json

echo "📡 Creating Kinesis Firehose delivery stream..."

# Get account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create Firehose delivery stream
aws firehose create-delivery-stream \
  --delivery-stream-name launchdarkly-experiments-stream \
  --delivery-stream-type DirectPut \
  --s3-destination-configuration \
  "RoleARN=arn:aws:iam::${ACCOUNT_ID}:role/launchdarkly-firehose-role,BucketARN=arn:aws:s3:::$BUCKET_NAME,Prefix=experiments/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/,ErrorOutputPrefix=errors/,BufferingHints={SizeInMBs=1,IntervalInSeconds=60},CompressionFormat=GZIP,EncryptionConfiguration={NoEncryptionConfig=NoEncryption}"

echo "🧹 Cleaning up temporary files..."
rm -f firehose-trust-policy.json firehose-s3-policy.json

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy env.example to .env and fill in your credentials"
echo "2. Set FIREHOSE_STREAM_NAME=launchdarkly-experiments-stream in .env"
echo "3. Run: poetry run python main.py"
echo ""
echo "AWS Authentication Options:"
echo "- Option 1: Use your current SSO credentials (include AWS_SESSION_TOKEN)"
echo "- Option 2: Create IAM user with programmatic access (no session token needed)"
echo ""
echo "Your S3 bucket: s3://$BUCKET_NAME"
echo "Your Firehose stream: launchdarkly-experiments-stream"
echo "Your AWS region: $AWS_REGION"
