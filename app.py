from flask import Flask, render_template, abort, request, jsonify
import requests

app = Flask(__name__)

# Base API URL (adjust if needed)
API_URL = "https://611vkfrpca.execute-api.us-east-2.amazonaws.com/products"

def get_product(product_id):
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        data = response.json()
        for product in data.get("items", []):
            if product["productId"] == product_id:
                return product
    except requests.exceptions.RequestException as e:
        print(f"Error fetching product data: {e}")
    return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/database')
def new_page():
    return render_template('database.html')

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'GET':
        return render_template('checkout.html')

    # POST request: process checkout
    cart = request.json.get("cart", [])
    if not cart:
        return jsonify({"error": "Cart is empty"}), 400

    # Process each cart item
    for item in cart:
        product_id = item.get("productId")
        quantity = item.get("quantity")
        if not product_id or not quantity:
            return jsonify({"error": "Invalid cart item"}), 400

        try:
            response = requests.post(
                f"{API_URL}/{product_id}/inventory",
                params={"quantity": -quantity, "remarks": "Sold Product"}
            )
            if response.status_code != 200:
                return jsonify({"error": f"Failed to purchase product with id {product_id}"}), 500
        except requests.exceptions.RequestException as e:
            print(f"Checkout error for product {product_id}: {e}")
            return jsonify({"error": f"Error processing checkout for product {product_id}"}), 500

    return jsonify({"message": "Purchase successful!"}), 200

@app.route('/product/<product_id>')
def product_detail(product_id):
    product = get_product(product_id)
    if not product:
        abort(404)
    return render_template('product_detail.html', product=product)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
