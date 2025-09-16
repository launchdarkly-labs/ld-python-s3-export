import boto3
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any

class FirehoseSender:
    def __init__(self, stream_name: str = None):
        """
        Initialize Firehose client
        
        Args:
            stream_name: Name of the Kinesis Firehose delivery stream
        """
        self.stream_name = stream_name or os.getenv('FIREHOSE_STREAM_NAME')
        if not self.stream_name:
            raise ValueError("Firehose stream name must be provided via parameter or FIREHOSE_STREAM_NAME env var")
        
        # Initialize Firehose client
        self.firehose_client = boto3.client(
            'firehose',
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
    
    def _extract_context_data(self, context):
        """
        Extract only the user-defined context data (excluding internal LD properties)
        
        Args:
            context: LaunchDarkly context object
            
        Returns:
            dict: Dictionary containing only the user-defined context attributes
        """
        context_data = {}
        
        # Extract basic attributes that are always present
        context_data["key"] = getattr(context, 'key', None)
        context_data["kind"] = getattr(context, 'kind', None)
        
        # Get the context as a dictionary to access user-defined attributes
        try:
            # Convert context to dict to get user-defined attributes
            context_dict = context.to_dict() if hasattr(context, 'to_dict') else {}
            
            # Only include user-defined attributes (exclude internal LD properties)
            internal_props = {
                'private_attributes',
                'DEFAULT_KIND', 'MULTI_KIND', 'error', 'fully_qualified_key', 
                'individual_context_count', 'multiple', 'valid'
            }
            
            for attr_name, value in context_dict.items():
                if attr_name not in internal_props and self._is_json_serializable(value):
                    context_data[attr_name] = value
                    
        except Exception:
            # Fallback: try to get name if available
            if hasattr(context, 'name') and context.name:
                context_data["name"] = context.name
        
        return context_data
    
    def _is_json_serializable(self, value):
        """
        Check if a value can be serialized to JSON
        
        Args:
            value: Value to check
            
        Returns:
            bool: True if serializable, False otherwise
        """
        try:
            json.dumps(value)
            return True
        except (TypeError, ValueError):
            return False
    
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
        
        # Convert to JSON string
        record_data = json.dumps(event_data) + '\n'  # Add newline for Firehose
        
        try:
            # Send to Firehose
            response = self.firehose_client.put_record(
                DeliveryStreamName=self.stream_name,
                Record={'Data': record_data}
            )
            
            print(f"Successfully sent experiment event to Firehose. Record ID: {response['RecordId']}")
            return True
            
        except Exception as e:
            print(f"Error sending to Firehose: {e}")
            return False
    
    def send_batch_events(self, events: list):
        """
        Send multiple events in a batch (more efficient for high volume)
        
        Args:
            events: List of event data dictionaries
        """
        if not events:
            return
        
        # Prepare records for batch
        records = []
        for event in events:
            record_data = json.dumps(event) + '\n'
            records.append({'Data': record_data})
        
        try:
            # Send batch to Firehose
            response = self.firehose_client.put_record_batch(
                DeliveryStreamName=self.stream_name,
                Records=records
            )
            
            print(f"Successfully sent {len(events)} events to Firehose")
            if response.get('FailedPutCount', 0) > 0:
                print(f"Failed to send {response['FailedPutCount']} records")
            
            return response
            
        except Exception as e:
            print(f"Error sending batch to Firehose: {e}")
            return None
