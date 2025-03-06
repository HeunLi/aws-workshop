import boto3
import os
import json
from utils.decimal_encoder import DecimalEncoder

class EventbridgeEvent:
    def __init__(self, detail_type, payload):
        """
        Initialize an EventBridge event
        
        Args:
            detail_type (str): The detail type of the event
            payload (dict): The event payload to send
        """
        self.detail_type = detail_type
        self.payload = payload
        self.source = "com.johnbons.products"
        self.event_bus_name = "custom-johnbons-event-bus-2"
        
    def send(self):
        """Send the event to EventBridge"""
        client = boto3.client('events', region_name='us-east-2')
        
        response = client.put_events(
            Entries=[
                {
                    'Source': self.source,
                    'DetailType': self.detail_type,
                    'Detail': json.dumps(self.payload, cls=DecimalEncoder),
                    'EventBusName': self.event_bus_name
                }
            ]
        )
        
        return response