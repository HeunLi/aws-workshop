import json
import boto3
from utils.decimal_encoder import DecimalEncoder

def send_message_to_queue(queue_name: str, message: dict, region: str = 'us-east-2'):
    sqs = boto3.resource('sqs', region_name=region)
    queue = sqs.get_queue_by_name(QueueName=queue_name)
    queue.send_message(MessageBody=json.dumps(message, cls=DecimalEncoder))
