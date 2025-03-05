import json

def hello(event, context):
    body = {
        "message": "We are team John Bons and this is the hello world"
    }
    return {
        "statusCode": 200,
        "body": json.dumps(body)
    }
