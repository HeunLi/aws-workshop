import json
import csv
import logging
import urllib
import time
import os
import boto3
import botocore.exceptions
from decimal import Decimal

from utils.decimal_encoder import DecimalEncoder
from utils.generate_code import generate_code
from models.sqs_service import send_message_to_queue
from models.logging_service import log_product_creation

TABLE_NAME = os.environ.get('DYNAMODB_TABLE')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_all_products(event, context):
    table_name = TABLE_NAME
    
    # Explicitly set the region
    dynamodb = boto3.resource("dynamodb", region_name="us-east-2")
    table = dynamodb.Table(table_name)

    try:
        items = []
        response = table.scan()

        # Handle pagination if data is more than 1MB
        while 'LastEvaluatedKey' in response:
            items.extend(response.get("Items", []))
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        
        # Add remaining items
        items.extend(response.get("Items", []))

        return_body = {"items": items, "status": "success"}

        return {"statusCode": 200, "body": json.dumps(return_body, cls=DecimalEncoder)}

    except botocore.exceptions.BotoCoreError as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
    
    except botocore.exceptions.ClientError as e:
        return {"statusCode": 500, "body": json.dumps({"error": e.response['Error']['Message']})}
    
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": "Internal Server Error", "details": str(e)})}


def create_one_product(event, context):
    body = json.loads(event["body"], parse_float=Decimal)
    
    table_name = TABLE_NAME
    dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
    table = dynamodb.Table(table_name)
    
    table.put_item(Item=body)
    
    response = {"statusCode": 200, "body": json.dumps(body, cls=DecimalEncoder)}
    
    sqs = boto3.client('sqs', region_name='us-east-2')
    queue = sqs.get_queue_by_name(QueueName='products-queue-johnbons-sqs')
    response = queue.send_message(MessageBody=json.dumps(body, cls=DecimalEncoder))

    # Log the event to CloudWatch
    log_client = boto3.client("logs", region_name="us-east-2")
    log_group_name = "/aws/lambda/product-creation-logs"
    log_stream_name = time.strftime("%Y/%m/%d")

    # Ensure log group exists
    try:
        log_client.create_log_group(logGroupName=log_group_name)
    except log_client.exceptions.ResourceAlreadyExistsException:
        pass

    # Ensure log stream exists
    try:
        log_client.create_log_stream(logGroupName=log_group_name, logStreamName=log_stream_name)
    except log_client.exceptions.ResourceAlreadyExistsException:
        pass

    # Log the product creation
    log_client.put_log_events(
        logGroupName=log_group_name,
        logStreamName=log_stream_name,
        logEvents=[{
            "timestamp": int(time.time() * 1000),
            "message": f"Product created: {body['productId']}"
        }]
    )

    return response

def get_one_product(event, context):
    table_name = TABLE_NAME
    dynamodb = boto3.resource("dynamodb", region_name="us-east-2")
    table = dynamodb.Table(table_name)

    # Debugging print to check the event received
    print("Received event:", json.dumps(event, indent=2))

    # Extract the productId from the API Gateway event
    path_params = event.get("pathParameters")
    if not path_params or "productId" not in path_params:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Bad Request: productId is required"})
        }

    product_id = path_params["productId"]

    # Corrected Key to match DynamoDB schema
    response = table.get_item(Key={"productId": product_id})

    # Check if the product exists
    if "Item" not in response:
        return {
            "statusCode": 404,
            "body": json.dumps({"message": "Product not found"})
        }

    return {
        "statusCode": 200,
        "body": json.dumps(response["Item"], cls=DecimalEncoder)
    }

def delete_one_product(event, context):
    table_name = TABLE_NAME
    dynamodb = boto3.resource("dynamodb", region_name="us-east-2")
    table = dynamodb.Table(table_name)

    # Debugging print to check the event received
    print("Received event:", json.dumps(event, indent=2))

    # Extract the productId from the API Gateway event
    path_params = event.get("pathParameters")
    if not path_params or "productId" not in path_params:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Bad Request: productId is required"})
        }

    product_id = path_params["productId"]

    # Attempt to delete the item
    response = table.delete_item(Key={"productId": product_id})

    return {
        "statusCode": 200,
        "body": json.dumps({"message": f"Product {product_id} deleted successfully"})
    }

def update_one_product(event, context):
    table_name = TABLE_NAME
    dynamodb = boto3.resource("dynamodb", region_name="us-east-2")
    table = dynamodb.Table(table_name)

    # Debugging print to check the event received
    print("Received event:", json.dumps(event, indent=2))

    # Extract productId from path parameters
    path_params = event.get("pathParameters")
    if not path_params or "productId" not in path_params:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Bad Request: productId is required"})
        }

    product_id = path_params["productId"]

    # Parse the request body for the updated attributes
    try:
        body = json.loads(event["body"], parse_float=Decimal)
    except (TypeError, json.JSONDecodeError):
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Invalid JSON body"})
        }

    # Ensure there's at least one field to update
    if not body:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Bad Request: No update data provided"})
        }

    # Build the UpdateExpression dynamically
    update_expression = "SET " + ", ".join(f"#{k} = :{k}" for k in body.keys())
    expression_attribute_names = {f"#{k}": k for k in body.keys()}  # Escape reserved keywords
    expression_attribute_values = {f":{k}": v for k, v in body.items()}

    # Update the item in DynamoDB
    response = table.update_item(
        Key={"productId": product_id},
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expression_attribute_names, 
        ExpressionAttributeValues=expression_attribute_values,
        ReturnValues="ALL_NEW"
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Product updated successfully",
            "updatedAttributes": response.get("Attributes")
        }, cls=DecimalEncoder)
    }

def batch_create_products(event, context):
    print("File uploaded trigger")
    print(event)
    
    print("Extract file location from event payload")
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])

    # Ensure only files from for_create/ folder are processed
    if not key.startswith("for_create/"):
        print(f"Skipping file {key} as it is not in the for_create/ folder")
        return {"statusCode": 400, "body": json.dumps({"message": "Invalid file location"})}

    localFilename = f'/tmp/{key.split("/")[-1]}'  # Extract filename only
    s3_client = boto3.client('s3', region_name='us-east-2')
    
    print("Downloading file to /tmp folder")
    s3_client.download_file(bucket, key, localFilename)
    
    print("Reading CSV file and inserting into DynamoDB...")
    
    with open(localFilename, 'r') as f:
        csv_reader = csv.DictReader(f)
        table_name = TABLE_NAME
        dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
        table = dynamodb.Table(table_name)
        
        for row in csv_reader:
            table.put_item(Item=row)
    
    print("All products have been added successfully!")
    return {"statusCode": 200, "body": json.dumps({"message": "Products added successfully"})}

def batch_delete_products(event, context):
    print("File uploaded trigger for deletion")
    print(event)
    
    print("Extract file location from event payload")
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])

    # Ensure only files from for_delete/ folder are processed
    if not key.startswith("for_delete/"):
        print(f"Skipping file {key} as it is not in the for_delete/ folder")
        return {"statusCode": 400, "body": json.dumps({"message": "Invalid file location"})}

    localFilename = f'/tmp/{key.split("/")[-1]}'  # Extract filename only
    s3_client = boto3.client('s3', region_name='us-east-2')
    
    print("Downloading file to /tmp folder")
    s3_client.download_file(bucket, key, localFilename)
    
    print("Reading CSV file and deleting products from DynamoDB...")

    with open(localFilename, 'r') as f:
        csv_reader = csv.reader(f)
        table_name = TABLE_NAME
        dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
        table = dynamodb.Table(table_name)

        for row in csv_reader:
            product_id = row[0]  # Assuming each row contains only one column: productId
            print(f"Deleting productId: {product_id}")

            table.delete_item(Key={"productId": product_id})

    print("All products listed in the file have been deleted!")
    return {"statusCode": 200, "body": json.dumps({"message": "Products deleted successfully"})}

def receive_message_from_sqs(event, context):
    fieldnames = ["productId", "brand_name", "product_name", "price", "quantity"]
    file_randomized_prefix = generate_code("pycon_", 8)
    file_name = f'/tmp/product_created_{file_randomized_prefix}.csv'
    bucket = "products-s3bucket-johnbons-sqs"
    object_name = f'product_created_{file_randomized_prefix}.csv'

    with open(file_name, 'w') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        for payload in event["Records"]:
            json_payload = json.loads(payload["body"])
            writer.writerow(json_payload)

    s3_client = boto3.client('s3')
    s3_client.upload_file(file_name, bucket, object_name)
    return {"statusCode": 200, "body": json.dumps({"message": "SQS messages processed successfully"})}
