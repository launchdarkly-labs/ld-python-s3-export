# LaunchDarkly Experiment Data Export to S3

A reference implementation showing how to integrate LaunchDarkly experiment evaluation data with AWS S3 using Kinesis Firehose. This enables real-time streaming of experiment data to your analytics platform.

## Overview

- LD SDK is configured with a flag [after_evaluation hook](https://launchdarkly-python-sdk.readthedocs.io/en/latest/api-main.html#module-ldclient.hook)
- The hook instatiates a FirehoseSender class at application start, a `boto3` client is created
- When a flag is evaluated, the `boto3` client is used to send data to the selected AWS S3 bucket

The project mainly focuses in configuring LaunchDarkly Python SDK so it generates analytics events capturing details about the evaluated flags, the variations that were served, and the context instances that were evaluated. This project includes a simple setup with AWS Firehose and S3 as the destination of those events. The project includes a `setup.sh` bash script that can be used to provision the necessary infrastructure in AWS. This is primarily meant for reference and as a proof of concept, it's not intended for production-ready implementation - your AWS instrumentation will likely be different.

Importing data from the S3 bucket to your analytics platform of choice is not in scope of this project. That said, a high-level guidance on importing the data to Databricks can be found in `DATABRICKS_INTEGRATION.md`. Note this part was not tested.

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

## Step-by-step Guide

### 1. Define a class that will be used by the flag evaluation hook

```python
class FlagEvaluationHook(Hook):
    def __init__(self):
        # Initialize Firehose sender
        try:
            self.firehose_sender = FirehoseSender()
            print("Firehose sender initialized successfully")
        except Exception as e:
            print(f"Failed to initialize Firehose sender: {e}")
            self.firehose_sender = None
    
    @property
    def metadata(self) -> Metadata:
        return Metadata(name="flag-evaluation-hook")

    def after_evaluation(self, evaluation_context, data, evaluation_detail):
        """
        Hook method called after every flag evaluation.
        """
        # Check if the user is in an experiment looking at the evaluation_detail > reason > inExperiment
        if (evaluation_detail.reason and 
            'inExperiment' in evaluation_detail.reason and 
            evaluation_detail.reason['inExperiment']):
            
            # Send experiment event to Firehose
            if self.firehose_sender:
                success = self.firehose_sender.send_experiment_event(evaluation_context, evaluation_detail)
                if success:
                    print(f"Successfully sent experiment event to Firehose")
                else:
                    print(f"Failed to send experiment event to Firehose")
            else:
                print(f"Firehose sender not available - skipping event send")
        else:
            print(f"User is not in an experiment for flag {evaluation_context.key}")
        
        return data
```

### 2. Add `after_evaluation` hook to your LD SDK config: 

```python
example_analytics_hook = FlagEvaluationHook()
ldclient.set_config(Config(sdk_key, hooks=[example_analytics_hook]))
```

### 3. Send the evaluation details to AWS S3

Inside the FirehoseSender class, initialize the AWS Firehose client (boto3), compose the analytics event, and send it to AWS S3. An example event payload:

```python
def send_experiment_event(self, evaluation_context, evaluation_detail):
        """
        Send experiment evaluation event to Firehose
        
        Args:
            evaluation_context: Contextual information that will be provided to handlers during evaluation series.
            evaluation_detail: The result of a flag evaluation with information about how it was calculated.
        """
        # Prepare the event data
        event_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "flag_key": evaluation_context.key,
            "evaluation_context": self._extract_context_data(evaluation_context.context),
            "flag_value": evaluation_detail.value,
            "variation_index": getattr(evaluation_detail, 'variation_index', None),
            "reason_kind": evaluation_detail.reason.get('kind') if evaluation_detail.reason else None,
            "metadata": {
                "source": "launchdarkly-python-hook",
                "version": "1.0"
            }
        }
```

For a full working example, check the [firehose_sender file](firehose_sender.py).

## Demo: Testing the Integration

This section shows how to test the integration locally. For production use, integrate the hook code into your existing application.

### Quick Test Setup

```bash
git clone <repository-url>
cd hello-python
poetry install
```

### Configure Environment

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
AWS_SESSION_TOKEN=your-aws-session-token # Only required when using temporary credentials (such as SSO); leave empty when using permanent IAM user credentials

# Kinesis Firehose Configuration
FIREHOSE_STREAM_NAME=launchdarkly-experiments-stream
```

### AWS Authentication Options

**Option 1: Temporary Credentials (SSO, STS, IAM Roles)**
- Include `AWS_SESSION_TOKEN` in your `.env` file
- Get credentials from AWS Console or `aws sso login`
- Credentials expire and need to be refreshed

**Option 2: Permanent IAM User Credentials**
- Create IAM user with programmatic access
- Use only `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
- Leave `AWS_SESSION_TOKEN` empty
- Credentials don't expire (unless rotated)

### Automated AWS Resource Setup

Use the provided setup script to create all required AWS resources:

```bash
chmod +x setup.sh
./setup.sh
```

This creates:
- S3 bucket for experiment data
- IAM role for Firehose with S3 permissions
- Kinesis Firehose delivery stream with partitioning

### Manual AWS Resource Setup

If you prefer to create resources manually or integrate with existing infrastructure:

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
  "RoleARN=arn:aws:iam::${ACCOUNT_ID}:role/launchdarkly-firehose-role,BucketARN=arn:aws:s3:::your-launchdarkly-experiments-bucket,Prefix=experiments/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/,ErrorOutputPrefix=errors/,BufferingHints={SizeInMBs=1,IntervalInSeconds=60},CompressionFormat=GZIP,EncryptionConfiguration={NoEncryptionConfig=NoEncryption}"
```

### Test the Integration

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
│   │   │   │   ├── hour=14/
│   │   │   │   │   ├── launchdarkly-experiments-stream-1-2024-01-15-14-00-00-abc123.json.gz
│   │   │   │   │   └── launchdarkly-experiments-stream-1-2024-01-15-14-05-00-def456.json.gz
│   │   │   │   └── hour=15/
│   │   │   └── day=16/
│   │   └── month=02/
│   └── errors/
│       └── failed-records.json.gz
```

**Note**: Data is partitioned by `year/month/day/hour` for efficient querying. The Firehose configuration uses dynamic partitioning: `experiments/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/`

**File Naming**: Files are automatically named by Kinesis Firehose using the pattern: `{stream-name}-{partition}-{timestamp}-{uuid}.gz` where:
- `stream-name`: Your Firehose delivery stream name (e.g., `launchdarkly-experiments-stream`)
- `partition`: Partition number (usually 1)
- `timestamp`: `YYYY-MM-DD-HH-MM-SS` format
- `uuid`: Unique identifier for the file
- `.gz`: GZIP compression applied automatically

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
  "reason_kind": "FALLTHROUGH",
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
The default configuration uses hourly partitioning for optimal query performance. Modify the `Prefix` parameter for different partitioning:
- **Hourly (Default)**: `experiments/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/`
- **Daily**: `experiments/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/`
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

## License

This project is licensed under the Apache-2.0 License.