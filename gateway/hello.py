import json


def hello(event, context):
    body = {
        "message": "We are team Jamby and this is the hello world",
    }

    print("I added a pretty little print here for debugging")

    response = {"statusCode": 200, "body": json.dumps(body)}

    return response
 