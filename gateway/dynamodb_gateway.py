import json
import csv
import logging
import urllib
import time
import os
import boto3
import botocore.exceptions
from decimal import Decimal
from boto3.dynamodb.conditions import Key
from decimal import Decimal
from models.eventbridge_event import EventbridgeEvent
from utils.decimal_encoder import DecimalEncoder
from utils.generate_code import generate_code
from models.sqs_service import send_message_to_queue
from models.logging_service import log_product_creation

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class ProductService:
    """Service class for handling product-related operations in DynamoDB"""
    
    def __init__(self):
        self.table_name = os.environ.get('DYNAMODB_TABLE')
        self.inventory_table_name = "ProductInventory-chall-johnbons2"
        self.region = "us-east-2"
        self.dynamodb = boto3.resource("dynamodb", region_name=self.region)
        self.product_table = self.dynamodb.Table(self.table_name)
        self.inventory_table = self.dynamodb.Table(self.inventory_table_name)
        self.log_client = boto3.client("logs", region_name=self.region)
        self.s3_client = boto3.client('s3', region_name=self.region)
    
    def get_all_products(self, event, context):
        """Retrieve all products from DynamoDB"""
        try:
            items = []
            response = self.product_table.scan()

            # Handle pagination if data is more than 1MB
            while 'LastEvaluatedKey' in response:
                items.extend(response.get("Items", []))
                response = self.product_table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            
            # Add remaining items
            items.extend(response.get("Items", []))

            return_body = {"items": items, "status": "success"}

            # Send event to EventBridge
            self._send_products_event(len(items))
            
            # Log the product retrieval
            self._log_product_retrieval(len(items))

            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"  # Ensure correct content type
                },
                "body": json.dumps(return_body, cls=DecimalEncoder)
            }

        except botocore.exceptions.BotoCoreError as e:
            return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
        
        except botocore.exceptions.ClientError as e:
            return {"statusCode": 500, "body": json.dumps({"error": e.response['Error']['Message']})}
        
        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"error": "Internal Server Error", "details": str(e)})}
    
    def create_one_product(self, event, context):
        """Create a single product in DynamoDB"""
        body = json.loads(event["body"], parse_float=Decimal)
        
        # Save product to DynamoDB
        self.product_table.put_item(Item=body)
        
        # Send message to SQS
        self._send_product_to_sqs(body)
        
        # Send event to EventBridge
        self._send_event_to_eventbridge(body)
        
        # Log the product creation
        self._log_product_creation(body)
        
        return {"statusCode": 200, "body": json.dumps(body, cls=DecimalEncoder)}

    
    def get_one_product(self, event, context):
        """Retrieve a single product by ID, including inventory data"""
        # Extract the productId from the API Gateway event
        path_params = event.get("pathParameters")
        if not path_params or "productId" not in path_params:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Bad Request: productId is required"})
            }

        product_id = path_params["productId"]

        # Get the product details
        response = self.product_table.get_item(Key={"productId": product_id})

        # Check if the product exists
        if "Item" not in response:
            return {
                "statusCode": 404,
                "body": json.dumps({"message": "Product not found"})
            }
        
        product = response["Item"]
        
        # Get inventory transactions for this product
        try:
            inventory_response = self.inventory_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('productId').eq(product_id)
            )
            
            inventory_items = inventory_response.get('Items', [])
            
            # Calculate total stock by summing all quantity values
            total_stock = sum(Decimal(item.get('quantity', 0)) for item in inventory_items)
            
            # Add inventory information to product
            product['current_stock'] = total_stock
            product['inventory_history'] = inventory_items
            
        except Exception as e:
            # If there's an error with inventory, still return the product but with a note
            product['current_stock'] = "Error fetching inventory"
            product['inventory_error'] = str(e)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"  # Ensure the correct content type
            },
            "body": json.dumps(product, cls=DecimalEncoder)
        }
        
    def get_one_product_by_name(self, event, context):
        """
        Retrieve a single product by product_name using a GSI.
        Expects a query parameter 'product_name' in the event.
        """
        logger.info("Received event: %s", json.dumps(event))
        
        query_params = event.get("queryStringParameters") or {}
        logger.info("Query parameters: %s", json.dumps(query_params))
        
        if "product_name" not in query_params:
            logger.error("Bad Request: product_name is not provided in query parameters")
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Bad Request: product_name is required"})
            }
        
        product_name = query_params["product_name"]
        logger.info("Searching for product with product_name: %s", product_name)
        
        # Query the table using the GSI on product_name
        try:
            response = self.product_table.query(
                IndexName="product_name-index",
                KeyConditionExpression=Key("product_name").eq(product_name)
            )
            logger.info("DynamoDB query response: %s", json.dumps(response, default=str))
        except Exception as e:
            logger.exception("Error querying product_table with product_name %s: %s", product_name, e)
            return {
                "statusCode": 500,
                "body": json.dumps({"message": "Internal Server Error", "error": str(e)})
            }
        
        items = response.get("Items", [])
        logger.info("Query returned %d items", len(items))
        
        if not items:
            logger.warning("No product found with product_name: %s", product_name)
            return {
                "statusCode": 404,
                "body": json.dumps({"message": "Product not found"})
            }
        
        # Assuming product_name is unique, take the first item
        product = items[0]
        logger.info("Found product: %s", json.dumps(product, default=str))
        
        # Retrieve and attach inventory details using the product's productId
        try:
            inventory_response = self.inventory_table.query(
                KeyConditionExpression=Key('productId').eq(product.get("productId"))
            )
            logger.info("Inventory query response: %s", json.dumps(inventory_response, default=str))
            inventory_items = inventory_response.get('Items', [])
            total_stock = sum(Decimal(item.get('quantity', 0)) for item in inventory_items)
            product['current_stock'] = total_stock
            product['inventory_history'] = inventory_items
        except Exception as e:
            logger.exception("Error fetching inventory for productId %s: %s", product.get("productId"), e)
            product['current_stock'] = "Error fetching inventory"
            product['inventory_error'] = str(e)
        
        logger.info("Returning product with inventory info: %s", json.dumps(product, default=str))
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(product, cls=DecimalEncoder)
        }
    
    def add_stocks_to_product(self, event, context):
        """Add inventory transaction and update product quantity"""
    
        # Extract productId from path parameters
        path_params = event.get("pathParameters")
        if not path_params or "productId" not in path_params:
            logger.error("productId is required in pathParameters")
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Bad Request: productId is required"})
            }
    
        product_id = path_params["productId"]
        logger.info("Updating inventory for productId: %s", product_id)
        
        # Verify product exists
        product_response = self.product_table.get_item(Key={"productId": product_id})
        if "Item" not in product_response:
            logger.warning("Product %s not found", product_id)
            return {
                "statusCode": 404,
                "body": json.dumps({"message": "Product not found"})
            }
        
        product = product_response["Item"]
    
        # Determine input parameters
        # Prioritize queryStringParameters if quantity is provided there, otherwise try JSON body
        input_data = {}
        if event.get("queryStringParameters") and event["queryStringParameters"].get("quantity") is not None:
            input_data = event["queryStringParameters"]
            logger.info("Using input from query parameters: %s", json.dumps(input_data))
        elif event.get("body"):
            try:
                input_data = json.loads(event["body"], parse_float=Decimal)
                logger.info("Using input from JSON body: %s", json.dumps(input_data, default=str))
            except (TypeError, json.JSONDecodeError) as e:
                logger.exception("Error parsing JSON body: %s", e)
                return {
                    "statusCode": 400,
                    "body": json.dumps({"message": "Invalid JSON body"})
                }
        else:
            logger.error("No input provided. Neither query parameters nor body found.")
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Bad Request: Input is required via query parameters or JSON body"})
            }
    
        # Validate quantity
        if "quantity" not in input_data:
            logger.error("Quantity parameter is missing from the input")
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Quantity is required"})
            }
        
        try:
            quantity_change = Decimal(str(input_data["quantity"]))  # Convert string (or number) to Decimal
            logger.info("Quantity change: %s", str(quantity_change))
        except Exception as e:
            logger.exception("Quantity conversion error: %s", e)
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Quantity must be a number"})
            }
        
        # Get the current quantity (default to 0 if missing)
        current_quantity = Decimal(product.get("quantity", 0))
        new_quantity = current_quantity + quantity_change
        logger.info("Current quantity: %s, New quantity: %s", str(current_quantity), str(new_quantity))
        
        # Ensure it doesn't go below 0
        if new_quantity < 0:
            logger.error("New quantity cannot be negative")
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Cannot reduce quantity below 0"})
            }
        
        # Update product's quantity in product_table
        try:
            self.product_table.update_item(
                Key={"productId": product_id},
                UpdateExpression="SET quantity = :q",
                ExpressionAttributeValues={":q": new_quantity}
            )
            logger.info("Updated product quantity to %s for productId %s", str(new_quantity), product_id)
        except Exception as e:
            logger.exception("Error updating product quantity: %s", e)
            return {
                "statusCode": 500,
                "body": json.dumps({"message": "Error updating product quantity", "error": str(e)})
            }
        
        # Log inventory transaction
        inventory_item = {
            "productId": product_id,
            "datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "quantity": quantity_change,
            "remarks": input_data.get("remarks", "")
        }
        try:
            self.inventory_table.put_item(Item=inventory_item)
            logger.info("Logged inventory transaction: %s", json.dumps(inventory_item, default=str))
        except Exception as e:
            logger.exception("Error logging inventory transaction: %s", e)
            return {
                "statusCode": 500,
                "body": json.dumps({"message": "Error logging inventory transaction", "error": str(e)})
            }
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Inventory updated for product {product_id}",
                "new_quantity": str(new_quantity),
                "transaction": inventory_item
            }, cls=DecimalEncoder)
        }
    
        
    def delete_one_product(self, event, context):
        """Delete a single product by ID"""
        # Extract the productId from the API Gateway event
        path_params = event.get("pathParameters")
        if not path_params or "productId" not in path_params:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Bad Request: productId is required"})
            }

        product_id = path_params["productId"]

        # Attempt to delete the item
        self.product_table.delete_item(Key={"productId": product_id})

        return {
            "statusCode": 200,
            "body": json.dumps({"message": f"Product {product_id} deleted successfully"})
        }
    
    def update_one_product(self, event, context):
        """Update a single product's attributes"""
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
        expression_attribute_names = {f"#{k}": k for k in body.keys()}
        expression_attribute_values = {f":{k}": v for k, v in body.items()}

        # Update the item in DynamoDB
        response = self.product_table.update_item(
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
    
    def batch_create_products(self, event, context):
        """Process uploaded CSV file to create multiple products"""
        print("File uploaded trigger")
        
        # Extract file location from event payload
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])

        # Ensure only files from for_create/ folder are processed
        if not key.startswith("for_create/"):
            print(f"Skipping file {key} as it is not in the for_create/ folder")
            return {"statusCode": 400, "body": json.dumps({"message": "Invalid file location"})}

        localFilename = f'/tmp/{key.split("/")[-1]}'  # Extract filename only
        
        print("Downloading file to /tmp folder")
        self.s3_client.download_file(bucket, key, localFilename)
        
        print("Reading CSV file and inserting into DynamoDB...")
        
        with open(localFilename, 'r') as f:
            csv_reader = csv.DictReader(f)
            
            for row in csv_reader:
                self.product_table.put_item(Item=row)
        
        print("All products have been added successfully!")
        return {"statusCode": 200, "body": json.dumps({"message": "Products added successfully"})}
    
    def batch_delete_products(self, event, context):
        """Process uploaded CSV file to delete multiple products"""
        print("File uploaded trigger for deletion")
        
        # Extract file location from event payload
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])

        # Ensure only files from for_delete/ folder are processed
        if not key.startswith("for_delete/"):
            print(f"Skipping file {key} as it is not in the for_delete/ folder")
            return {"statusCode": 400, "body": json.dumps({"message": "Invalid file location"})}

        localFilename = f'/tmp/{key.split("/")[-1]}'  # Extract filename only
        
        print("Downloading file to /tmp folder")
        self.s3_client.download_file(bucket, key, localFilename)
        
        print("Reading CSV file and deleting products from DynamoDB...")

        with open(localFilename, 'r') as f:
            csv_reader = csv.reader(f)

            for row in csv_reader:
                product_id = row[0]  # Assuming each row contains only one column: productId
                print(f"Deleting productId: {product_id}")

                self.product_table.delete_item(Key={"productId": product_id})

        print("All products listed in the file have been deleted!")
        return {"statusCode": 200, "body": json.dumps({"message": "Products deleted successfully"})}
    
    def receive_message_from_sqs(self, event, context):
        """Process SQS messages and create CSV file"""
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

        self.s3_client.upload_file(file_name, bucket, object_name)
        return {"statusCode": 200, "body": json.dumps({"message": "SQS messages processed successfully"})}
    
    # Private helper methods
    def _send_products_event(self, count):
        """Send event to EventBridge"""
        event_payload = {"total_products": count, "timestamp": time.time()}
        event = EventbridgeEvent("products_fetched", event_payload)
        event.send()
        
    def _send_event_to_eventbridge(self, product_data):
        """Send product creation event to EventBridge"""
        event_client = boto3.client('events')
        
        response = event_client.put_events(
            Entries=[
                {
                    'EventBusName': 'custom-johnbons-event-bus2',
                    'Source': 'com.johnbons.products',
                    'DetailType': 'create_product',
                    'Detail': json.dumps(product_data, cls=DecimalEncoder)
                }
            ]
        )
        
        # Optional: handle response
        if response.get('FailedEntryCount', 0) > 0:
            # Handle failed entries if needed
            print(f"Failed to send event to EventBridge: {response}")
    
    def _log_product_retrieval(self, count):
        """Log product retrieval to CloudWatch"""
        log_group_name = "/aws/lambda/python-serverless-johnbons-dev-getAllProducts"
        log_stream_name = time.strftime("%Y/%m/%d")
        
        # Ensure log group exists
        self._ensure_log_group_exists(log_group_name)
        
        # Ensure log stream exists
        self._ensure_log_stream_exists(log_group_name, log_stream_name)
        
        # Log the product retrieval
        logger.info(f"Retrieved {count} products")
    
    def _send_product_to_sqs(self, product_data):
        """Send product data to SQS queue"""
        sqs = boto3.resource('sqs', region_name=self.region)
        queue = sqs.get_queue_by_name(QueueName='products-queue-johnbons-sqs')
        
        # Create a new message
        queue.send_message(MessageBody=json.dumps(product_data, cls=DecimalEncoder))
    
    def _log_product_creation(self, product_data):
        """Log product creation to CloudWatch"""
        logger.info(f"Creating product: {product_data}")
        logger.info(json.dumps({"message":"Product Created"}))

        # Log the event to CloudWatch
        log_group_name = "/aws/lambda/product-creation-logs"
        log_stream_name = time.strftime("%Y/%m/%d")

        # Ensure log group and stream exist
        self._ensure_log_group_exists(log_group_name)
        self._ensure_log_stream_exists(log_group_name, log_stream_name)

        # Log the product creation
        self.log_client.put_log_events(
            logGroupName=log_group_name,
            logStreamName=log_stream_name,
            logEvents=[{
                "timestamp": int(time.time() * 1000),
                "message": f"Product created: {product_data['productId']}"
            }]
        )
    
    def _ensure_log_group_exists(self, log_group_name):
        """Ensure CloudWatch log group exists"""
        try:
            self.log_client.create_log_group(logGroupName=log_group_name)
        except self.log_client.exceptions.ResourceAlreadyExistsException:
            pass
    
    def _ensure_log_stream_exists(self, log_group_name, log_stream_name):
        """Ensure CloudWatch log stream exists"""
        try:
            self.log_client.create_log_stream(logGroupName=log_group_name, logStreamName=log_stream_name)
        except self.log_client.exceptions.ResourceAlreadyExistsException:
            pass

    def get_lowest_quantity(self, event, context):
        """Retrieve the product with the lowest quantity along with its product ID and product name."""
        try:
            # Scan the table and project only the required fields
            response = self.product_table.scan(
                ProjectionExpression="productId, product_name, quantity"
            )
            items = response.get("Items", [])
            
            # Handle pagination if data is more than 1MB
            while 'LastEvaluatedKey' in response:
                response = self.product_table.scan(
                    ProjectionExpression="productId, product_name, quantity",
                    ExclusiveStartKey=response["LastEvaluatedKey"]
                )
                items.extend(response.get("Items", []))
            
            # Build the product response
            if not items:
                product = {"lowest_quantity": None, "product_id": None, "product_name": None}
            else:
                # Determine the item with the lowest quantity.
                # If a product is missing a quantity, it defaults to 0.
                lowest_item = min(items, key=lambda x: Decimal(x.get("quantity", 0)))
                product = {
                    "lowest_quantity": lowest_item.get("quantity", 0),
                    "product_id": lowest_item.get("productId"),
                    "product_name": lowest_item.get("product_name")
                }
            
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"  # Ensure the correct content type
                },
                "body": json.dumps(product, cls=DecimalEncoder)
            }
        except Exception as e:
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({"error": str(e)})
            }

# Lambda handler functions that use the ProductService class
product_service = ProductService()

def get_all_products(event, context):
    return product_service.get_all_products(event, context)

def create_one_product(event, context):
    return product_service.create_one_product(event, context)

def get_one_product(event, context):
    return product_service.get_one_product(event, context)

def add_stocks_to_product(event, context):
    return product_service.add_stocks_to_product(event, context)

def delete_one_product(event, context):
    return product_service.delete_one_product(event, context)

def update_one_product(event, context):
    return product_service.update_one_product(event, context)

def batch_create_products(event, context):
    return product_service.batch_create_products(event, context)

def batch_delete_products(event, context):
    return product_service.batch_delete_products(event, context)

def receive_message_from_sqs(event, context):
    return product_service.receive_message_from_sqs(event, context)
    
def get_lowest_quantity(event, context):
    return product_service.get_lowest_quantity(event, context)
    
def get_one_product_by_name(event, context):
    return product_service.get_one_product_by_name(event, context)