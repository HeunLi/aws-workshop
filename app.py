from flask import Flask, render_template, abort, request
import requests

app = Flask(__name__)

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

@app.route('/checkout')
def checkout():
    return render_template('checkout.html')

@app.route('/product/<product_id>')
def product_detail(product_id):
    product = get_product(product_id)
    if not product:
        abort(404)
    return render_template('product_detail.html', product=product)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)