import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def log_products_events(event, context):
    """
    Logs products-related events received from EventBridge
    """
    logger.info(f"Received products event: {json.dumps(event)}")
    
    detail_type = event.get('detail-type')
    source = event.get('source')
    detail = event.get('detail')
    
    logger.info(f"Event source: {source}")
    logger.info(f"Event type: {detail_type}")
    logger.info(f"Event detail: {json.dumps(detail)}")
    
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Event processed successfully"})
    }