# my_flask_app.py

from flask import Flask, render_template, g
from sqlalchemy import create_engine, text
from flask import request, redirect, url_for
import datetime
import random, string

app = Flask(__name__)

# === Database connection string ===
DATABASEURI = "postgresql://yw4384:367602@34.148.223.31/proj1part2"
engine = create_engine(DATABASEURI)

# === Connect to the database before each request ===
@app.before_request
def before_request():
    try:
        g.conn = engine.connect()
    except:
        g.conn = None

# === Close the connection after each request ===
@app.teardown_request
def teardown_request(exception):
    try:
        g.conn.close()
    except Exception:
        pass

@app.route('/')
def index():
    return render_template('index.html')

# === Products page: display list of products ===
@app.route('/products')
def products():
    cursor = g.conn.execute(text("SELECT product_id, name, category, price, stock_quantity, rating FROM Products"))
    result = []
    for row in cursor:
        result.append({
            "product_id": row[0],
            "name": row[1],
            "category": row[2],
            "price": row[3],
            "stock_quantity": row[4],
            "rating": row[5]
        })
    return render_template("products.html", products=result)

@app.route('/cart', methods=['GET', 'POST'])
def cart():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        return redirect(url_for('cart', user_id=user_id))

    user_id = request.args.get('user_id', type=int)

    if user_id is None:
        return render_template("cart_input.html")

    try:
        query = text("""
            SELECT 
                sci.cart_id,
                sc.user_id,
                p.product_id,
                p.name,
                p.price,
                sci.quantity,
                sci.added_to_cart_date
            FROM shopping_cart sc
            JOIN shopping_cart_items sci ON sc.cart_id = sci.cart_id
            JOIN products p ON sci.product_id = p.product_id
            WHERE sc.user_id = :uid
        """)
        cursor = g.conn.execute(query, {"uid": user_id})

        cart_items = []
        total_price = 0

        for row in cursor:
            item = {
                "cart_id": row[0],
                "user_id": row[1],
                "product_id": row[2],
                "name": row[3],
                "price": float(row[4]),
                "quantity": row[5],
                "added_to_cart_date": row[6],
                "subtotal": float(row[4]) * row[5]
            }
            total_price += item["subtotal"]
            cart_items.append(item)

        return render_template("cart.html", cart=cart_items, total=total_price, user_id=user_id)

    except Exception as e:
        return f"<h3>Error loading cart: {str(e)}</h3>"


@app.route("/orders", methods=["GET", "POST"])
def orders():
    if request.method == "POST":
        user_id = request.form.get("user_id")  #Extracted from the user input of your front-end page (HTML form)
        return redirect(url_for("orders", user_id=user_id))

    user_id = request.args.get("user_id", type=int)
    if user_id is None:
        return render_template("orders_input.html")  

    try:
        cursor = g.conn.execute(text(f"""
            SELECT o.order_id, o.category, o.total_price, o.payment_method,
                   o.order_date, o.status, o.shipping_address,
                   oi.product_id, oi.quantity
            FROM Orders o
            JOIN Order_items oi ON o.order_id = oi.order_id
            WHERE o.user_id = {user_id}
            ORDER BY o.order_date DESC;
        """))

        orders_dict = {}
        for row in cursor:
            order_id = row[0]
            if order_id not in orders_dict:
                orders_dict[order_id] = {
                    "order_id": order_id,
                    "category": row[1],
                    "total_price": row[2],
                    "payment_method": row[3],
                    "order_date": row[4],
                    "status": row[5],
                    "shipping_address": row[6],
                    "items": []
                }
            orders_dict[order_id]["items"].append({
                "product_id": row[7],
                "quantity": row[8]
            })

        return render_template("orders.html", orders=orders_dict.values(), user_id=user_id)

    except Exception as e:
        return f"<h3>Error loading orders: {str(e)}</h3>"

def generate_review_id():
    return 'R' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=13))



@app.route('/search', methods=['GET', 'POST'])
def search():
    results = []
    keyword = ""
    if request.method == 'POST':
        keyword = request.form['keyword']
        with engine.connect() as conn:
            cursor = conn.execute(
                text(f"""
                    SELECT p.product_id, p.name, p.price, p.rating
                    FROM Products p
                    LEFT JOIN Reviews r ON p.product_id = r.product_id
                    WHERE p.name ILIKE '%{keyword}%'
                    GROUP BY p.product_id, p.name, p.price, p.rating, p.stock_quantity
                    ORDER BY 
                        p.rating DESC,
                        COUNT(r.review_id) DESC,
                        p.stock_quantity DESC
                """)
		    )
            results = cursor.fetchall()
    return render_template('search.html', results=results, keyword=keyword)


@app.route('/product/<product_id>', methods=['GET', 'POST'])
def product_detail(product_id):
    with engine.connect() as conn:
        # query product info
        result = conn.execute(
            text("""
                SELECT product_id, name, category, price, stock_quantity, rating
                FROM Products
                WHERE product_id = :pid
            """),
            {"pid": product_id}
        ).fetchone()

        if result is None:
            return f"<h2>No product found with ID {product_id}</h2>"

        product = {
            "product_id": result[0],
            "name": result[1],
            "category": result[2],
            "price": result[3],
            "stock_quantity": result[4],
            "rating": result[5],
        }

        # Query comments, must also be in “with”
        review_query = conn.execute(
            text("""
                SELECT u.name, r.rating, r.review_text, r.review_date
                FROM Reviews r
                JOIN Users u ON r.user_id = u.user_id
                WHERE r.product_id = :pid
                ORDER BY r.review_date DESC
            """),
            {"pid": product_id}
        )
        reviews = review_query.fetchall()

    return render_template("product.html", product=product, reviews=reviews)

@app.route('/submit_review/<product_id>', methods=['POST'])
def submit_review(product_id):
    user_id = request.form['user_id']
    rating = request.form['rating']
    review_text = request.form['review_text']
    review_date = datetime.date.today()

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO Reviews (review_id, user_id, product_id, rating, review_text, review_date)
                VALUES (:rid, :uid, :pid, :rating, :text, :date)
            """),
            {	"rid": generate_review_id(),
                "uid": user_id,
                "pid": product_id,
                "rating": rating,
                "text": review_text,
                "date": datetime.date.today()
            }
        )

    return redirect(url_for('product_detail', product_id=product_id))




# === Run the Flask app ===
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8111, debug=True)

