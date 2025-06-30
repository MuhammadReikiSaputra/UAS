from flask import Flask, jsonify, send_from_directory, request, abort
from flask_cors import CORS
import os
import logging
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
import sqlite3
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder='static')
app.wsgi_app = ProxyFix(app.wsgi_app)
CORS(app)

# Database setup
def get_db_connection():
    conn = sqlite3.connect('cakeshop.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create products table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        price INTEGER NOT NULL,
        image TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create orders table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT NOT NULL,
        customer_email TEXT NOT NULL,
        customer_phone TEXT,
        total_amount INTEGER NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create order_items table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        product_id INTEGER,
        quantity INTEGER NOT NULL,
        price INTEGER NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders (id),
        FOREIGN KEY (product_id) REFERENCES products (id)
    )
    ''')
    
    # Check if products table is empty and seed initial data if needed
    cursor.execute('SELECT COUNT(*) FROM products')
    count = cursor.fetchone()[0]
    
    if count == 0:
        # Seed initial product data
        initial_products = [
            {
                "name": "Kue Coklat Lapis",
                "description": "Kue coklat lezat dengan lapisan ganache yang kaya",
                "price": 250000,
                "image": "https://images.unsplash.com/photo-1578985545062-69928b1d9587"
            },
            {
                "name": "Kue Stroberi",
                "description": "Kue lembut dengan krim stroberi segar di atasnya",
                "price": 280000,
                "image": "https://images.unsplash.com/photo-1563729784474-d77dbb933a9e"
            },
            {
                "name": "Red Velvet",
                "description": "Kue red velvet dengan krim keju yang lezat",
                "price": 300000,
                "image": "https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445"
            }
        ]
        
        for product in initial_products:
            cursor.execute(
                'INSERT INTO products (name, description, price, image) VALUES (?, ?, ?, ?)',
                (product['name'], product['description'], product['price'], product['image'])
            )
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

# Initialize database on startup
init_db()

# API Routes
@app.route('/api/products', methods=['GET'])
def get_products():
    try:
        conn = get_db_connection()
        products = conn.execute('SELECT * FROM products').fetchall()
        conn.close()
        
        # Convert to list of dictionaries
        product_list = [dict(product) for product in products]
        return jsonify(product_list)
    except Exception as e:
        logger.error(f"Error fetching products: {str(e)}")
        return jsonify({"error": "Failed to fetch products"}), 500

@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    try:
        conn = get_db_connection()
        product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
        conn.close()
        
        if product is None:
            return jsonify({"error": "Product not found"}), 404
            
        return jsonify(dict(product))
    except Exception as e:
        logger.error(f"Error fetching product {product_id}: {str(e)}")
        return jsonify({"error": "Failed to fetch product"}), 500

@app.route('/api/products', methods=['POST'])
def add_product():
    if not request.json:
        abort(400, description="Request must be JSON")
        
    required_fields = ['name', 'price']
    for field in required_fields:
        if field not in request.json:
            abort(400, description=f"Missing required field: {field}")
    
    try:
        new_product = {
            'name': request.json['name'],
            'description': request.json.get('description', ''),
            'price': request.json['price'],
            'image': request.json.get('image', '')
        }
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO products (name, description, price, image) VALUES (?, ?, ?, ?)',
            (new_product['name'], new_product['description'], new_product['price'], new_product['image'])
        )
        conn.commit()
        
        # Get the ID of the newly inserted product
        new_product_id = cursor.lastrowid
        
        # Fetch the complete product data
        product = conn.execute('SELECT * FROM products WHERE id = ?', (new_product_id,)).fetchone()
        conn.close()
        
        logger.info(f"New product added: {new_product['name']}")
        return jsonify(dict(product)), 201
    except Exception as e:
        logger.error(f"Error adding product: {str(e)}")
        return jsonify({"error": "Failed to add product"}), 500

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    if not request.json:
        abort(400, description="Request must be JSON")
        
    try:
        conn = get_db_connection()
        
        # Check if product exists
        product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
        if product is None:
            conn.close()
            return jsonify({"error": "Product not found"}), 404
        
        # Update fields that are present in the request
        updates = {}
        if 'name' in request.json:
            updates['name'] = request.json['name']
        if 'description' in request.json:
            updates['description'] = request.json['description']
        if 'price' in request.json:
            updates['price'] = request.json['price']
        if 'image' in request.json:
            updates['image'] = request.json['image']
            
        if not updates:
            conn.close()
            return jsonify({"error": "No fields to update"}), 400
            
        # Build the SQL query dynamically
        set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values())
        values.append(product_id)
        
        conn.execute(f'UPDATE products SET {set_clause} WHERE id = ?', values)
        conn.commit()
        
        # Fetch the updated product
        updated_product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
        conn.close()
        
        logger.info(f"Product updated: {product_id}")
        return jsonify(dict(updated_product))
    except Exception as e:
        logger.error(f"Error updating product {product_id}: {str(e)}")
        return jsonify({"error": "Failed to update product"}), 500

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    try:
        conn = get_db_connection()
        
        # Check if product exists
        product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
        if product is None:
            conn.close()
            return jsonify({"error": "Product not found"}), 404
            
        conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
        conn.commit()
        conn.close()
        
        logger.info(f"Product deleted: {product_id}")
        return jsonify({"message": "Product deleted successfully"})
    except Exception as e:
        logger.error(f"Error deleting product {product_id}: {str(e)}")
        return jsonify({"error": "Failed to delete product"}), 500

# Order endpoints
@app.route('/api/orders', methods=['POST'])
def create_order():
    if not request.json:
        abort(400, description="Request must be JSON")
        
    required_fields = ['customer_name', 'customer_email', 'items']
    for field in required_fields:
        if field not in request.json:
            abort(400, description=f"Missing required field: {field}")
    
    if not request.json['items'] or not isinstance(request.json['items'], list):
        abort(400, description="Items must be a non-empty array")
    
    try:
        conn = get_db_connection()
        
        # Calculate total amount and validate items
        total_amount = 0
        order_items = []
        
        for item in request.json['items']:
            if 'product_id' not in item or 'quantity' not in item:
                conn.close()
                return jsonify({"error": "Each item must have product_id and quantity"}), 400
                
            product_id = item['product_id']
            quantity = item['quantity']
            
            if quantity <= 0:
                conn.close()
                return jsonify({"error": "Quantity must be positive"}), 400
                
            # Get product price
            product = conn.execute('SELECT price FROM products WHERE id = ?', (product_id,)).fetchone()
            if product is None:
                conn.close()
                return jsonify({"error": f"Product with ID {product_id} not found"}), 404
                
            price = product['price']
            item_total = price * quantity
            total_amount += item_total
            
            order_items.append({
                'product_id': product_id,
                'quantity': quantity,
                'price': price
            })
        
        # Create order
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO orders (customer_name, customer_email, customer_phone, total_amount, status) VALUES (?, ?, ?, ?, ?)',
            (
                request.json['customer_name'],
                request.json['customer_email'],
                request.json.get('customer_phone', ''),
                total_amount,
                'pending'
            )
        )
        
        order_id = cursor.lastrowid
        
        # Create order items
        for item in order_items:
            cursor.execute(
                'INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)',
                (order_id, item['product_id'], item['quantity'], item['price'])
            )
            
        conn.commit()
        
        # Fetch the complete order with items
        order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
        items = conn.execute('SELECT * FROM order_items WHERE order_id = ?', (order_id,)).fetchall()
        
        conn.close()
        
        order_dict = dict(order)
        order_dict['items'] = [dict(item) for item in items]
        
        logger.info(f"New order created: {order_id}")
        return jsonify(order_dict), 201
    except Exception as e:
        logger.error(f"Error creating order: {str(e)}")
        return jsonify({"error": "Failed to create order"}), 500

@app.route('/api/orders', methods=['GET'])
def get_orders():
    try:
        conn = get_db_connection()
        orders = conn.execute('SELECT * FROM orders ORDER BY created_at DESC').fetchall()
        
        result = []
        for order in orders:
            order_dict = dict(order)
            items = conn.execute('SELECT * FROM order_items WHERE order_id = ?', (order['id'],)).fetchall()
            order_dict['items'] = [dict(item) for item in items]
            result.append(order_dict)
            
        conn.close()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching orders: {str(e)}")
        return jsonify({"error": "Failed to fetch orders"}), 500

@app.route('/api/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    try:
        conn = get_db_connection()
        order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
        
        if order is None:
            conn.close()
            return jsonify({"error": "Order not found"}), 404
            
        order_dict = dict(order)
        items = conn.execute('SELECT * FROM order_items WHERE order_id = ?', (order_id,)).fetchall()
        order_dict['items'] = [dict(item) for item in items]
        
        conn.close()
        return jsonify(order_dict)
    except Exception as e:
        logger.error(f"Error fetching order {order_id}: {str(e)}")
        return jsonify({"error": "Failed to fetch order"}), 500

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    if not request.json or 'status' not in request.json:
        abort(400, description="Request must include status field")
        
    valid_statuses = ['pending', 'processing', 'completed', 'cancelled']
    if request.json['status'] not in valid_statuses:
        return jsonify({"error": f"Status must be one of: {', '.join(valid_statuses)}"}), 400
    
    try:
        conn = get_db_connection()
        
        # Check if order exists
        order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
        if order is None:
            conn.close()
            return jsonify({"error": "Order not found"}), 404
            
        conn.execute(
            'UPDATE orders SET status = ? WHERE id = ?',
            (request.json['status'], order_id)
        )
        conn.commit()
        
        # Fetch the updated order
        updated_order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
        items = conn.execute('SELECT * FROM order_items WHERE order_id = ?', (order_id,)).fetchall()
        
        conn.close()
        
        order_dict = dict(updated_order)
        order_dict['items'] = [dict(item) for item in items]
        
        logger.info(f"Order {order_id} status updated to {request.json['status']}")
        return jsonify(order_dict)
    except Exception as e:
        logger.error(f"Error updating order {order_id} status: {str(e)}")
        return jsonify({"error": "Failed to update order status"}), 500

# Static file serving
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_file(path):
    return send_from_directory('.', path)

# Error handlers
@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": error.description}), 400

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"Server error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # Check if SSL certificates exist
    ssl_context = None
    if os.path.exists('cert.pem') and os.path.exists('key.pem'):
        ssl_context = ('cert.pem', 'key.pem')
        logger.info("SSL certificates found, running with HTTPS")
    else:
        logger.warning("SSL certificates not found, running without HTTPS")
    
    # Get port from environment variable or use default
    port = int(os.environ.get('PORT', 8080))
    
    app.run(host='0.0.0.0', port=port, debug=False, ssl_context=ssl_context)