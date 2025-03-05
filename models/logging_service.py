import time
import boto3

def log_product_creation(product_id: str, region: str = 'us-east-2'):
    log_client = boto3.client("logs", region_name=region)
    log_group_name = "/aws/lambda/product-creation-logs"
    log_stream_name = time.strftime("%Y/%m/%d")
    
    # Create log group if it does not exist
    try:
        log_client.create_log_group(logGroupName=log_group_name)
    except log_client.exceptions.ResourceAlreadyExistsException:
        pass

    # Create log stream if it does not exist
    try:
        log_client.create_log_stream(logGroupName=log_group_name, logStreamName=log_stream_name)
    except log_client.exceptions.ResourceAlreadyExistsException:
        pass

    # Log the product creation event
    log_client.put_log_events(
        logGroupName=log_group_name,
        logStreamName=log_stream_name,
        logEvents=[{
            "timestamp": int(time.time() * 1000),
            "message": f"Product created: {product_id}"
        }]
    )
