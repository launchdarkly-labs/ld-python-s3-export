# Databricks Integration Guide

This guide provides general guidance for integrating LaunchDarkly experiment data with Databricks using Auto Loader.

## Important Note

This integration guide is provided as a starting point and has not been tested in a live Databricks environment. Please test thoroughly and adapt the queries to your specific setup before using in production.

## Overview

The LaunchDarkly experiment data is stored in S3 with the following structure:
```
s3://your-bucket/experiments/year=2024/month=01/day=15//hour=hh/experiment-data.json
```

Each JSON file contains one experiment event per line with this schema:
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

## Auto Loader Setup

### 1. Configure Auto Loader

```python
# Configure Auto Loader to read from S3
df = spark.readStream \
  .format("cloudFiles") \
  .option("cloudFiles.format", "json") \
  .option("cloudFiles.schemaLocation", "/tmp/launchdarkly-schema") \
  .option("cloudFiles.schemaEvolution", "true") \
  .load("s3://your-launchdarkly-experiments-bucket/experiments/")
```

### 2. Process the Data

```python
from pyspark.sql.functions import col, from_json, current_timestamp

# Extract and transform experiment data
experiment_events = df.select(
    col("timestamp"),
    col("flag_key"),
    col("flag_value"),
    col("evaluation_context.key").alias("user_key"),
    col("evaluation_context.kind").alias("context_kind"),
    col("evaluation_context.tier").alias("user_tier"),
    col("evaluation_context.country").alias("user_country"),
    col("variation_index"),
    current_timestamp().alias("processed_at")
)
```

### 3. Write to Delta Table

```python
# Write streaming data to Delta table
experiment_events.writeStream \
  .format("delta") \
  .outputMode("append") \
  .option("checkpointLocation", "/tmp/launchdarkly-checkpoint") \
  .table("launchdarkly_experiments")
```

## Sample Analysis Queries

### Experiment Participation by Flag

```sql
SELECT 
  flag_key,
  flag_value,
  COUNT(*) as participant_count,
  COUNT(DISTINCT user_key) as unique_users
FROM launchdarkly_experiments
GROUP BY flag_key, flag_value
ORDER BY flag_key, flag_value;
```

### User Tier Distribution

```sql
SELECT 
  flag_key,
  user_tier,
  COUNT(*) as count
FROM launchdarkly_experiments
WHERE user_tier IS NOT NULL
GROUP BY flag_key, user_tier
ORDER BY flag_key, count DESC;
```

### Geographic Distribution

```sql
SELECT 
  flag_key,
  user_country,
  COUNT(*) as participant_count
FROM launchdarkly_experiments
WHERE user_country IS NOT NULL
GROUP BY flag_key, user_country
ORDER BY flag_key, participant_count DESC;
```

### Daily Experiment Performance

```sql
SELECT 
  DATE(timestamp) as experiment_date,
  flag_key,
  flag_value,
  COUNT(*) as daily_participants
FROM launchdarkly_experiments
GROUP BY DATE(timestamp), flag_key, flag_value
ORDER BY experiment_date DESC, flag_key, flag_value;
```

## Batch Processing

For historical data analysis:

```python
# Read all historical data
historical_df = spark.read \
  .option("multiline", "true") \
  .json("s3://your-launchdarkly-experiments-bucket/experiments/")

# Perform batch analysis
experiment_summary = historical_df.groupBy("flag_key", "flag_value") \
  .count() \
  .orderBy("flag_key", "flag_value")
```

## Advanced Analytics

### A/B Test Statistical Analysis

```sql
-- Calculate conversion rates (requires additional conversion data)
WITH experiment_data AS (
  SELECT 
    flag_key,
    flag_value,
    user_key,
    timestamp
  FROM launchdarkly_experiments
),
conversions AS (
  -- Join with your conversion events table
  SELECT user_key, conversion_timestamp
  FROM your_conversions_table
)
SELECT 
  e.flag_key,
  e.flag_value,
  COUNT(DISTINCT e.user_key) as participants,
  COUNT(DISTINCT c.user_key) as conversions,
  ROUND(COUNT(DISTINCT c.user_key) * 100.0 / COUNT(DISTINCT e.user_key), 2) as conversion_rate
FROM experiment_data e
LEFT JOIN conversions c ON e.user_key = c.user_key 
  AND c.conversion_timestamp >= e.timestamp
GROUP BY e.flag_key, e.flag_value;
```

### Cohort Analysis

```sql
-- Analyze user behavior by experiment group
SELECT 
  flag_key,
  flag_value,
  user_tier,
  COUNT(DISTINCT user_key) as users,
  AVG(CAST(variation_index AS FLOAT)) as avg_variation
FROM launchdarkly_experiments
WHERE user_tier IS NOT NULL
GROUP BY flag_key, flag_value, user_tier
ORDER BY flag_key, flag_value, user_tier;
```

## Performance Optimization

### Partitioning Strategy

The S3 data is already partitioned by date and hour (`year=YYYY/month=MM/day=DD/hour=HH`). For better query performance:

1. **Use partition pruning** in your queries
2. **Consider additional partitioning** by `flag_key` if you have many flags
3. **Use Delta table partitioning** for frequently queried columns

### Example Optimized Query

```sql
-- Query specific date range and flag
SELECT *
FROM launchdarkly_experiments
WHERE flag_key = 'your-specific-flag'
  AND DATE(timestamp) BETWEEN '2024-01-01' AND '2024-01-31';
```

## Troubleshooting

### Common Issues

1. **Schema Evolution**: Enable `cloudFiles.schemaEvolution` for new context attributes
2. **Data Format**: Ensure JSON files are properly formatted (one JSON per line)
3. **Permissions**: Verify S3 bucket access permissions for Databricks
4. **Checkpointing**: Use unique checkpoint locations for different streams

### Monitoring

- Monitor Auto Loader metrics in Databricks
- Set up alerts for failed data loads
- Check S3 access logs for data arrival

## Resources

- [Databricks Auto Loader Documentation](https://docs.databricks.com/ingestion/auto-loader/index.html)
- [Delta Lake Documentation](https://docs.delta.io/)
- [Spark SQL Functions](https://spark.apache.org/docs/latest/api/sql/)

## Support

For issues with this integration:
1. Check Databricks documentation
2. Verify S3 permissions and data format
3. Test with small data samples first
4. Contact your Databricks administrator for platform-specific issues
