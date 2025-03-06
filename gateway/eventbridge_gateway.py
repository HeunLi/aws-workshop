import boto3
import os
import json
from utils.decimal_encoder import DecimalEncoder

class EventbridgeEvent:
    def __init__(self, detail_type, detail):
        self.detail_type = detail_type
        self.detail = detail
        self.source = "com.yourcompany.products"  # Customize this source name
        self.event_bus_name = os.environ.get('EVENT_BUS_NAME', 'default')
        
    def send(self):
        """Send the event to EventBridge"""
        client = boto3.client('events', region_name='us-east-2')
        
        response = client.put_events(
            Entries=[
                {
                    'Source': self.source,
                    'DetailType': self.detail_type,
                    'Detail': json.dumps(self.detail, cls=DecimalEncoder),
                    'EventBusName': self.event_bus_name
                }
            ]
        )
        
        return response