import boto3
import time
import json

def push_product_creation_log(product_id, pid=123):
    logs_client = boto3.client('logs', region_name='us-east-2')
    log_group_name = "ProductCreationLogs"
    log_stream_name = "ProductCreationStream"
    
    # Create the log stream if it doesn't exist
    try:
        logs_client.create_log_stream(logGroupName=log_group_name, logStreamName=log_stream_name)
    except logs_client.exceptions.ResourceAlreadyExistsException:
        pass

    # Get the current sequence token for the log stream (if any)
    response = logs_client.describe_log_streams(
        logGroupName=log_group_name,
        logStreamNamePrefix=log_stream_name
    )
    log_streams = response.get('logStreams', [])
    sequence_token = None
    if log_streams and 'uploadSequenceToken' in log_streams[0]:
        sequence_token = log_streams[0]['uploadSequenceToken']

    # Create a log event in JSON format
    log_event = {
        "timestamp": int(time.time() * 1000),
        "message": json.dumps({
            "event": "product_created",
            "pid": pid,
            "data": {
                "productId": product_id,
                # Add any additional product details if needed
            }
        })
    }

    # Prepare parameters for put_log_events
    put_log_params = {
        "logGroupName": log_group_name,
        "logStreamName": log_stream_name,
        "logEvents": [log_event]
    }
    if sequence_token:
        put_log_params["sequenceToken"] = sequence_token

    # Push the log event to CloudWatch Logs
    put_response = logs_client.put_log_events(**put_log_params)
    return put_response
