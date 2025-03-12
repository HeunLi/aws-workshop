import json
from gateway.dynamodb_gateway import (
    get_all_products,
    create_one_product,
    get_one_product,
    delete_one_product,
    update_one_product,
    add_stocks_to_product,
    batch_create_products, 
    batch_delete_products,
    receive_message_from_sqs,
    get_lowest_quantity,
    get_one_product_by_name  # Newly added import
)

def handler(event, context):
    http_method = event.get("httpMethod")
    resource = event.get("resource")  # e.g., "/products", "/products/{productId}", etc.
    
    if resource == "/products":
        if http_method == "GET":
            return get_all_products(event, context)
        elif http_method == "POST":
            return create_one_product(event, context)
        else:
            return method_not_allowed()
            
    elif resource == "/products/{productId}":
        if http_method == "GET":
            return get_one_product(event, context)
        elif http_method == "PUT":
            return update_one_product(event, context)
        elif http_method == "DELETE":
            return delete_one_product(event, context)
        else:
            return method_not_allowed()
            
    elif resource == "/products/{productId}/inventory":
        if http_method == "POST":
            return add_stocks_to_product(event, context)
        else:
            return method_not_allowed()

    # New endpoint for searching product by product_name
    elif resource == "/products/by-name":
        if http_method == "GET":
            return get_one_product_by_name(event, context)
        else:
            return method_not_allowed()

    # New endpoint for retrieving the lowest quantity among products
    elif resource == "/products/lowest_quantity":
        if http_method == "GET":
            return get_lowest_quantity(event, context)
        else:
            return method_not_allowed()
            
    else:
        return {"statusCode": 404, "body": json.dumps({"message": "Not Found"})}
        
def method_not_allowed():
    return {"statusCode": 405, "body": json.dumps({"message": "Method Not Allowed"})}
