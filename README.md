# LaunchDarkly Experiment Data Export to S3

This project demonstrates how to export LaunchDarkly experiment evaluation data to AWS S3 using Kinesis Firehose. The data can then be consumed by analytics platforms like Databricks.

## Overview

This project focuses on the **S3 export** portion of the data pipeline. It captures experiment evaluation events from LaunchDarkly's Python SDK using hooks and streams them to S3 in real-time.

**What this project provides:**
- ✅ **Real-time experiment data streaming** to S3
- ✅ **Flexible context parsing** for different context types  
- ✅ **Partitioned data storage** for efficient querying
- ✅ **Complete working example** with setup automation

**What you need to configure separately:**
- ⚠️ **Import from S3 to your analytics platform** (see DATABRICKS_INTEGRATION.md for guidance on Databrics)

## Architecture

```
LaunchDarkly SDK → Python Hook → Kinesis Firehose → S3
                                                      ↓
                                              [Your Analytics Platform]
```

## Prerequisites

- **AWS Account** with permissions to create and manage:
  - Kinesis Firehose delivery streams
  - S3 buckets
  - IAM roles and policies
- **LaunchDarkly Account** with:
  - SDK key
  - Feature flags with experiments enabled
- **Python 3.9+** with Poetry
- **Analytics Platform** (Databricks, Snowflake, etc.) - not included in this project

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd hello-python
poetry install
```

### 2. Configure Environment

```bash
cp env.example .env
```

Edit `.env` with your credentials:

```bash
# LaunchDarkly Configuration
LAUNCHDARKLY_SDK_KEY=your-launchdarkly-sdk-key
LAUNCHDARKLY_FLAG_KEY=your-feature-flag-key

# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key

# Kinesis Firehose Configuration
FIREHOSE_STREAM_NAME=launchdarkly-experiments-stream
```

### 3. Setup AWS Resources

#### Create S3 Bucket
```bash
aws s3 mb s3://your-launchdarkly-experiments-bucket
```

#### Create IAM Role for Firehose
```bash
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
cat > firehose-s3-policy.json << 'EOF'
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
        "arn:aws:s3:::your-launchdarkly-experiments-bucket",
        "arn:aws:s3:::your-launchdarkly-experiments-bucket/*"
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
```

#### Create Kinesis Firehose Delivery Stream
```bash
# Get your account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create Firehose delivery stream
aws firehose create-delivery-stream \
  --delivery-stream-name launchdarkly-experiments-stream \
  --delivery-stream-type DirectPut \
  --s3-destination-configuration \
  "RoleARN=arn:aws:iam::${ACCOUNT_ID}:role/launchdarkly-firehose-role,BucketARN=arn:aws:s3:::your-launchdarkly-experiments-bucket,Prefix=experiments/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/,ErrorOutputPrefix=errors/,BufferingHints={SizeInMBs=1,IntervalInSeconds=60},CompressionFormat=UNCOMPRESSED,EncryptionConfiguration={NoEncryptionConfig=NoEncryption}"
```

### 4. Run the Application

```bash
poetry run python main.py
```

## Data Structure

### S3 Data Organization
```
s3://your-bucket/
├── experiments/
│   ├── year=2024/
│   │   ├── month=01/
│   │   │   ├── day=15/
│   │   │   │   ├── 2024-01-15-14-00-00-abc123.json
│   │   │   │   └── 2024-01-15-14-05-00-def456.json
│   │   │   └── day=16/
│   │   └── month=02/
│   └── errors/
│       └── failed-records.json
```

### Event Data Schema
Each event contains:
```json
{
  "timestamp": "2024-01-15T14:30:00.123456+00:00",
  "flag_key": "example-experiment-flag",
  "evaluation_context": {
    "key": "user-123",
    "kind": "user",
    "tier": "premium",
    "country": "US"
  },
  "flag_value": "treatment",
  "variation_index": 1,
  "metadata": {
    "source": "launchdarkly-python-hook",
    "version": "1.0"
  }
}
```

## Next Steps: Analytics Platform Integration

Once your data is flowing to S3, you'll need to configure your analytics platform to consume it.

### For Databricks Users

See [DATABRICKS_INTEGRATION.md](DATABRICKS_INTEGRATION.md) for guidance on:
- Auto Loader configuration
- Sample analysis queries  
- Performance optimization tips
- Troubleshooting guidance

**Note**: The Databricks integration guide is provided as a starting point and has not been tested. Please verify and adapt the configuration for your environment.

### For Other Platforms

The S3 data is stored in a standard JSON format that can be consumed by:
- **Snowflake** - Use external tables or COPY commands
- **BigQuery** - Use external data sources
- **Athena** - Query directly from S3
- **Custom applications** - Use AWS SDKs to read the JSON files

## Configuration Options

### Firehose Buffering
Adjust buffering settings in the Firehose configuration:
- `SizeInMBs`: Buffer size (1-128 MB)
- `IntervalInSeconds`: Buffer time (60-900 seconds)

### S3 Partitioning
Modify the `Prefix` parameter for different partitioning:
- **Daily**: `experiments/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/`
- **Hourly**: `experiments/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/`
- **Monthly**: `experiments/year=!{timestamp:yyyy}/month=!{timestamp:MM}/`

### Context Parsing
The integration automatically captures all user-defined context attributes. Internal LaunchDarkly properties are filtered out.

## Monitoring and Troubleshooting

### Check Data Flow
```bash
# Verify S3 data
aws s3 ls s3://your-launchdarkly-experiments-bucket/experiments/ --recursive

# Check Firehose metrics
aws firehose describe-delivery-stream --delivery-stream-name launchdarkly-experiments-stream
```

### Common Issues
1. **Expired AWS credentials**: Run `aws sso login` or refresh your credentials
2. **Permission denied**: Verify IAM role has proper S3 permissions
3. **Stream not found**: Ensure Firehose delivery stream exists and is active
4. **Data not appearing**: Check Firehose buffering settings and error logs

### CloudWatch Monitoring
- Monitor Firehose delivery metrics
- Set up alarms for failed deliveries
- Check S3 access logs for data arrival

## Customization

### Adding Custom Context Attributes
The integration automatically captures any custom attributes in your LaunchDarkly contexts:

```python
# In your LaunchDarkly context
context = Context.builder('user-123') \
  .kind('user') \
  .name('John Doe') \
  .set('tier', 'premium') \
  .set('country', 'US') \
  .set('subscription_id', 'sub_123') \
  .build()
```

All custom attributes will be automatically included in the S3 data.

### Modifying Event Schema
Edit `firehose_sender.py` to customize the event structure:

```python
def send_experiment_event(self, evaluation_context, flag):
    event_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "flag_key": evaluation_context.key,
        "evaluation_context": self._extract_context_data(evaluation_context.context),
        "flag_value": flag.value,
        "variation_index": getattr(flag, 'variation_index', None),
        # Add custom fields here
        "custom_field": "custom_value"
    }
```

## Security Considerations

- Use IAM roles with minimal required permissions
- Enable S3 server-side encryption if needed
- Consider VPC endpoints for private network access
- Implement proper access controls for S3 buckets

## Cost Optimization

- Use appropriate Firehose buffering settings
- Implement S3 lifecycle policies for data retention
- Consider data compression for large volumes
- Monitor and optimize partition sizes

## Support

For issues with this integration:
1. Check the troubleshooting section above
2. Review AWS CloudWatch logs
3. Verify LaunchDarkly hook configuration

## License

This project is licensed under the Apache-2.0 License.