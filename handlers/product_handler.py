import json
import sys
import os
# import aws_xray_sdk.core as xray
# from aws_xray_sdk.core import xray_recorder, patch_all
# from aws_xray_sdk.core import models as xray_models
from gateway.dynamodb_gateway import (
    get_all_products,
    create_one_product,
    get_one_product,
    delete_one_product,
    update_one_product,
    batch_create_products,
    batch_delete_products,
    receive_message_from_sqs,
)

# Patch AWS services (DynamoDB, SQS, etc.)
# patch_all()
# print("Python Path:", sys.path)
# print("Installed Packages:", os.listdir("/opt/python") if os.path.exists("/opt/python") else "No Layer Found")
# # Start tracing for AWS Lambda
# xray_recorder.configure(service="ProductService")
# @xray_recorder.capture("handle_get_product")
def handler(event, context):
    """
    This handler routes requests to the appropriate function in dynamodb_gateway.
    It assumes that API Gateway is set up with resource paths and HTTP methods.
    """
    segment = xray_recorder.begin_segment("ProductHandler")  # Start X-Ray segment
    http_method = event.get("httpMethod")
    resource = event.get("resource")  # e.g., "/products" or "/products/{productId}"
    # try:
    if resource == "/products":
        if http_method == "GET":
            return get_all_products(event, context)
        elif http_method == "POST":
            return create_one_product(event, context)
        else:
            return _method_not_allowed()
    elif resource == "/products/{productId}":
        if http_method == "GET":
            return get_one_product(event, context)
        elif http_method == "PUT":
            return update_one_product(event, context)
        elif http_method == "DELETE":
            return delete_one_product(event, context)
        else:
            return _method_not_allowed()
    else:
        return {"statusCode": 404, "body": json.dumps({"message": "Not Found"})}
except Exception as e:
     # Capture errors in X-Ray
    segment.add_exception(e)
    response = {"statusCode": 500, "body": json.dumps({"message": "Internal Server Error"})}
    # finally:
    #     xray_recorder.end_segment()  # End X-Ray segment
    
    # return response
        
def _method_not_allowed():
    return {"statusCode": 405, "body": json.dumps({"message": "Method Not Allowed"})}
