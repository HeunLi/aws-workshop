import json
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

def handler(event, context):
    """
    This handler routes requests to the appropriate function in dynamodb_gateway.
    It assumes that API Gateway is set up with resource paths and HTTP methods.
    """
    http_method = event.get("httpMethod")
    resource = event.get("resource")  # e.g., "/products" or "/products/{productId}"

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

def _method_not_allowed():
    return {"statusCode": 405, "body": json.dumps({"message": "Method Not Allowed"})}
