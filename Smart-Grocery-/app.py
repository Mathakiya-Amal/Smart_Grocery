from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db
from recommender import get_recommendations, get_popular_products, get_user_purchase_summary
import os
import re
import functools
import requests
import datetime
import secrets
import csv
import io
from datetime import timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())

# ── Decorators ────────────────────────────────────────────────────────────────

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def vendor_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("user_role") not in ("vendor", "admin"):
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("user_role") != "admin":
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_cart_count():
    if "user_id" not in session:
        return 0
    db = get_db()
    pipeline = [
        {"$match": {"user_id": session["user_id"]}},
        {"$group": {"_id": None, "total": {"$sum": "$quantity"}}}
    ]
    res = list(db.cart.aggregate(pipeline))
    return res[0]["total"] if res else 0

def set_session_from_user(user):
    session["user_id"] = user["_id"]
    session["user_name"] = user.get("name", "")
    session["user_email"] = user.get("email", "")
    session["user_role"] = user.get("role", "customer")

@app.context_processor
def inject_globals():
    return {
        "cart_count": get_cart_count(),
        "user": session.get("user_name", ""),
        "user_email": session.get("user_email", ""),
        "user_role": session.get("user_role", "customer"),
        "logged_in": "user_id" in session,
    }

# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        role = session.get("user_role", "customer")
        return redirect(url_for("vendor_dashboard") if role == "vendor" else url_for("admin_dashboard") if role == "admin" else url_for("index"))

    error = None
    if request.method == "POST":
        action = request.form.get("action", "login")
        db = get_db()

        if action == "signup":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if not name or not email or not password:
                error = "All fields are required."
            elif len(password) < 6:
                error = "Password must be at least 6 characters."
            else:
                if db.users.find_one({"email": email}):
                    error = "Email already registered."
                else:
                    # Generate an integer ID (since old code used SQLite autoincrement)
                    last_user = db.users.find_one(sort=[("_id", -1)])
                    new_id = (last_user["_id"] + 1) if last_user and isinstance(last_user["_id"], int) else 1
                    
                    user_doc = {
                        "_id": new_id,
                        "name": name,
                        "email": email,
                        "password_hash": generate_password_hash(password),
                        "role": "customer",
                        "phone": "",
                        "address": "",
                        "is_blocked": 0,
                        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    db.users.insert_one(user_doc)
                    set_session_from_user(user_doc)
                    return redirect(url_for("index"))
        else:
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = db.users.find_one({"email": email})
            if user and check_password_hash(user.get("password_hash", ""), password):
                if user.get("is_blocked"):
                    error = "Your account has been suspended. Contact support."
                else:
                    set_session_from_user(user)
                    role = session.get("user_role", "customer")
                    if role == "vendor":
                        return redirect(url_for("vendor_dashboard"))
                    elif role == "admin":
                        return redirect(url_for("admin_dashboard"))
                    return redirect(url_for("index"))
            else:
                error = "Invalid email or password."

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── Customer: Home & Products ─────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        recommendations = get_recommendations(session["user_id"])
        user_name = session.get("user_name", "")
        purchase_summary = get_user_purchase_summary(session["user_id"])
    else:
        recommendations = get_popular_products()
        user_name = ""
        purchase_summary = None
    return render_template("home.html",
        recommendations=recommendations,
        user_name=user_name,
        purchase_summary=purchase_summary
    )

@app.route("/products")
def products():
    db = get_db()
    category = request.args.get("category", "All")
    search = request.args.get("search", "").strip()
    sort = request.args.get("sort", "featured")

    query = {"is_approved": 1}
    if category and category != "All":
        query["category"] = category
    if search:
        regex = {"$regex": search, "$options": "i"}
        query["$or"] = [{"name": regex}, {"brand": regex}, {"category": regex}]

    sort_criteria = [("_id", 1)]
    if sort == "price_asc":
        sort_criteria = [("price", 1)]
    elif sort == "price_desc":
        sort_criteria = [("price", -1)]

    all_products = list(db.products.find(query).sort(sort_criteria))
    for p in all_products:
        p["id"] = p["_id"]

    categories_raw = db.products.distinct("category", {"is_approved": 1})
    categories = sorted([c for c in categories_raw if c])

    cart_items = {}
    if "user_id" in session:
        rows = db.cart.find({"user_id": session["user_id"]})
        cart_items = {r["product_id"]: r["quantity"] for r in rows}

    return render_template("products.html",
        products=all_products,
        categories=categories,
        selected_category=category,
        search=search,
        sort=sort,
        cart_items=cart_items
    )

# ── Cart ──────────────────────────────────────────────────────────────────────

@app.route("/cart")
@login_required
def cart():
    db = get_db()
    pipeline = [
        {"$match": {"user_id": session["user_id"]}},
        {"$lookup": {"from": "products", "localField": "product_id", "foreignField": "_id", "as": "product"}},
        {"$unwind": "$product"},
        {"$lookup": {"from": "users", "localField": "product.vendor_id", "foreignField": "_id", "as": "vendor"}},
        {"$unwind": {"path": "$vendor", "preserveNullAndEmptyArrays": True}}
    ]
    raw_items = list(db.cart.aggregate(pipeline))
    
    items = []
    for r in raw_items:
        vname = r.get("vendor", {}).get("name") if r.get("vendor") else 'Smart Grocery'
        items.append({
            "id": r["_id"],
            "quantity": r["quantity"],
            "product_id": r["product"]["_id"],
            "name": r["product"]["name"],
            "brand": r["product"].get("brand", ""),
            "price": r["product"]["price"],
            "unit": r["product"]["unit"],
            "image_url": r["product"]["image_url"],
            "vendor_id": r["product"].get("vendor_id"),
            "vendor_name": vname
        })
    
    items.sort(key=lambda x: (x["vendor_name"], x["name"]))

    subtotal = sum(i["price"] * i["quantity"] for i in items)
    delivery = 0.0 if subtotal >= 30 else 5.00
    tax = round(subtotal * 0.05, 2)
    total = round(subtotal + delivery + tax, 2)

    vendor_groups = {}
    for item in items:
        vname = item["vendor_name"]
        vendor_groups.setdefault(vname, []).append(item)
    multi_vendor = len(vendor_groups) > 1

    return render_template("cart.html",
        items=items, subtotal=round(subtotal, 2),
        delivery=delivery, tax=tax, total=total,
        vendor_groups=vendor_groups, multi_vendor=multi_vendor
    )

@app.route("/api/cart/add", methods=["POST"])
@login_required
def add_to_cart():
    data = request.get_json()
    product_id = data.get("product_id")
    if not product_id:
        return jsonify({"error": "Missing product_id"}), 400
    db = get_db()
    
    existing = db.cart.find_one({"user_id": session["user_id"], "product_id": product_id})
    if existing:
        db.cart.update_one({"_id": existing["_id"]}, {"$inc": {"quantity": 1}})
    else:
        last_cart = db.cart.find_one(sort=[("_id", -1)])
        new_id = (last_cart["_id"] + 1) if last_cart and isinstance(last_cart.get("_id"), int) else 1
        db.cart.insert_one({"_id": new_id, "user_id": session["user_id"], "product_id": product_id, "quantity": 1})
        
    return jsonify({"success": True, "cart_count": get_cart_count()})

@app.route("/api/cart/update", methods=["POST"])
@login_required
def update_cart():
    data = request.get_json()
    product_id = data.get("product_id")
    quantity = int(data.get("quantity", 1))
    db = get_db()
    
    if quantity <= 0:
        db.cart.delete_one({"user_id": session["user_id"], "product_id": product_id})
    else:
        db.cart.update_one(
            {"user_id": session["user_id"], "product_id": product_id},
            {"$set": {"quantity": quantity}}
        )
    return jsonify({"success": True, "cart_count": get_cart_count()})

@app.route("/api/cart/remove", methods=["POST"])
@login_required
def remove_from_cart():
    data = request.get_json()
    product_id = data.get("product_id")
    db = get_db()
    db.cart.delete_one({"user_id": session["user_id"], "product_id": product_id})
    return jsonify({"success": True, "cart_count": get_cart_count()})

# ── Orders ────────────────────────────────────────────────────────────────────

@app.route("/order-summary")
@login_required
def order_summary():
    db = get_db()
    pipeline = [
        {"$match": {"user_id": session["user_id"]}},
        {"$lookup": {"from": "products", "localField": "product_id", "foreignField": "_id", "as": "product"}},
        {"$unwind": "$product"},
        {"$lookup": {"from": "users", "localField": "product.vendor_id", "foreignField": "_id", "as": "vendor"}},
        {"$unwind": {"path": "$vendor", "preserveNullAndEmptyArrays": True}}
    ]
    raw_items = list(db.cart.aggregate(pipeline))
    
    items = []
    for r in raw_items:
        vname = r.get("vendor", {}).get("name") if r.get("vendor") else 'Smart Grocery'
        items.append({
            "quantity": r["quantity"],
            "product_id": r["product"]["_id"],
            "name": r["product"]["name"],
            "price": r["product"]["price"],
            "image_url": r["product"]["image_url"],
            "vendor_id": r["product"].get("vendor_id"),
            "vendor_name": vname
        })
    items.sort(key=lambda x: (x["vendor_name"], x["name"]))

    user = db.users.find_one({"_id": session["user_id"]})
    if user:
        user["id"] = user["_id"]

    if not items:
        return redirect(url_for("cart"))

    subtotal = sum(i["price"] * i["quantity"] for i in items)
    delivery = 0.0 if subtotal >= 30 else 2.99
    tax = round(subtotal * 0.08, 2)
    total = round(subtotal + delivery + tax, 2)

    vendor_groups = {}
    for item in items:
        vname = item["vendor_name"]
        vendor_groups.setdefault(vname, []).append(item)
    multi_vendor = len(vendor_groups) > 1

    return render_template("order_summary.html",
        items=items, subtotal=round(subtotal, 2),
        delivery=delivery, tax=tax, total=total,
        vendor_groups=vendor_groups, multi_vendor=multi_vendor,
        user=user
    )

@app.route("/place-order", methods=["POST"])
@login_required
def place_order():
    address = request.form.get("address", "").strip()
    pincode = request.form.get("pincode", "").strip()
    mobile = request.form.get("mobile", "").strip()

    errors = []
    if not address:
        errors.append("Delivery address is required.")
    if not re.fullmatch(r"\d{4,10}", pincode):
        errors.append("PIN code must be 4–10 digits.")
    if not re.fullmatch(r"[\d\s\+\-]{7,15}", mobile):
        errors.append("Mobile number must be 7–15 digits.")

    db = get_db()
    pipeline = [
        {"$match": {"user_id": session["user_id"]}},
        {"$lookup": {"from": "products", "localField": "product_id", "foreignField": "_id", "as": "product"}},
        {"$unwind": "$product"},
        {"$lookup": {"from": "users", "localField": "product.vendor_id", "foreignField": "_id", "as": "vendor"}},
        {"$unwind": {"path": "$vendor", "preserveNullAndEmptyArrays": True}}
    ]
    raw_items = list(db.cart.aggregate(pipeline))
    items = []
    for r in raw_items:
        vname = r.get("vendor", {}).get("name") if r.get("vendor") else 'Smart Grocery'
        items.append({
            "quantity": r["quantity"],
            "product_id": r["product"]["_id"],
            "name": r["product"]["name"],
            "price": r["product"]["price"],
            "image_url": r["product"]["image_url"],
            "vendor_id": r["product"].get("vendor_id"),
            "vendor_name": vname
        })

    if not items:
        return redirect(url_for("cart"))

    if errors:
        items.sort(key=lambda x: (x["vendor_name"], x["name"]))
        user = db.users.find_one({"_id": session["user_id"]})
        if user: user["id"] = user["_id"]
        subtotal = sum(i["price"] * i["quantity"] for i in items)
        delivery = 0.0 if subtotal >= 30 else 2.99
        tax = round(subtotal * 0.08, 2)
        total = round(subtotal + delivery + tax, 2)
        vendor_groups = {}
        for item in items:
            vendor_groups.setdefault(item["vendor_name"], []).append(item)
        return render_template("order_summary.html",
            items=items, subtotal=round(subtotal, 2),
            delivery=delivery, tax=tax, total=total,
            vendor_groups=vendor_groups, multi_vendor=len(vendor_groups) > 1,
            user=user, errors=errors,
            form_address=address, form_pincode=pincode, form_mobile=mobile
        )

    subtotal = sum(i["price"] * i["quantity"] for i in items)
    delivery = 0.0 if subtotal >= 30 else 2.99
    tax = round(subtotal * 0.08, 2)
    total = round(subtotal + delivery + tax, 2)

    last_og = db.order_groups.find_one(sort=[("_id", -1)])
    group_id = (last_og["_id"] + 1) if last_og and isinstance(last_og.get("_id"), int) else 1

    db.order_groups.insert_one({
        "_id": group_id,
        "user_id": session["user_id"],
        "total_amount": total,
        "delivery_fee": delivery,
        "tax": tax,
        "address": address,
        "pincode": pincode,
        "mobile": mobile,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    by_vendor = {}
    for item in items:
        key = (item["vendor_id"], item["vendor_name"])
        by_vendor.setdefault(key, []).append(item)

    for (vid, vname), vitems in by_vendor.items():
        vsub = sum(i["price"] * i["quantity"] for i in vitems)
        last_vo = db.vendor_orders.find_one(sort=[("_id", -1)])
        vo_id = (last_vo["_id"] + 1) if last_vo and isinstance(last_vo.get("_id"), int) else 1
        
        db.vendor_orders.insert_one({
            "_id": vo_id,
            "order_group_id": group_id,
            "vendor_id": vid,
            "vendor_name": vname,
            "subtotal": round(vsub, 2),
            "status": "pending",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        for item in vitems:
            last_oi = db.order_items.find_one(sort=[("_id", -1)])
            oi_id = (last_oi["_id"] + 1) if last_oi and isinstance(last_oi.get("_id"), int) else 1
            db.order_items.insert_one({
                "_id": oi_id,
                "order_id": group_id,
                "vendor_order_id": vo_id,
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "price": item["price"]
            })

    db.cart.delete_many({"user_id": session["user_id"]})
    return redirect(url_for("order_placed", group_id=group_id))

@app.route("/order-placed/<int:group_id>")
@login_required
def order_placed(group_id):
    db = get_db()
    group = db.order_groups.find_one({"_id": group_id, "user_id": session["user_id"]})
    if not group:
        return redirect(url_for("index"))
    
    group["id"] = group["_id"]
    vendor_orders_list = list(db.vendor_orders.find({"order_group_id": group_id}))
    for vo in vendor_orders_list:
        vo["id"] = vo["_id"]
        oi_list = list(db.order_items.find({"vendor_order_id": vo["_id"]}))
        line_items = []
        for oi in oi_list:
            p = db.products.find_one({"_id": oi["product_id"]})
            if p:
                line_items.append({
                    "quantity": oi["quantity"],
                    "price": oi["price"],
                    "name": p["name"],
                    "image_url": p["image_url"]
                })
        vo["line_items"] = line_items
        
    all_items = [i for vo in vendor_orders_list for i in vo["line_items"]]
    return render_template("order_placed.html",
        group=group, vendor_orders=vendor_orders_list, items=all_items
    )

@app.route("/orders")
@login_required
def my_orders():
    db = get_db()
    groups = list(db.order_groups.find({"user_id": session["user_id"]}).sort("created_at", -1))
    
    for g in groups:
        g["id"] = g["_id"]
        vendor_orders_list = list(db.vendor_orders.find({"order_group_id": g["_id"]}).sort("_id", 1))
        for vo in vendor_orders_list:
            vo["id"] = vo["_id"]
            oi_list = list(db.order_items.find({"vendor_order_id": vo["_id"]}))
            line_items = []
            for oi in oi_list:
                p = db.products.find_one({"_id": oi["product_id"]})
                if p:
                    line_items.append({
                        "quantity": oi["quantity"],
                        "name": p["name"],
                        "image_url": p["image_url"]
                    })
            vo["line_items"] = line_items
            
        g["vendor_orders"] = vendor_orders_list
        all_imgs = [i["image_url"] for vo in vendor_orders_list for i in vo["line_items"]]
        g["images"] = all_imgs[:4]
        g["item_count"] = sum(len(vo["line_items"]) for vo in vendor_orders_list)
        statuses = [vo["status"] for vo in vendor_orders_list]
        if all(s == "delivered" for s in statuses) if statuses else False:
            g["overall_status"] = "delivered"
        elif any(s == "shipped" for s in statuses):
            g["overall_status"] = "in transit"
        elif any(s == "confirmed" for s in statuses):
            g["overall_status"] = "confirmed"
        else:
            g["overall_status"] = "pending"

    return render_template("orders.html", orders=groups)

@app.route("/track/<int:group_id>")
@login_required
def track_order(group_id):
    db = get_db()
    group = db.order_groups.find_one({"_id": group_id, "user_id": session["user_id"]})
    if not group:
        return redirect(url_for("my_orders"))
        
    group["id"] = group["_id"]
    vendor_orders_list = list(db.vendor_orders.find({"order_group_id": group_id}).sort("_id", 1))
    for vo in vendor_orders_list:
        vo["id"] = vo["_id"]
        oi_list = list(db.order_items.find({"vendor_order_id": vo["_id"]}))
        line_items = []
        for oi in oi_list:
            p = db.products.find_one({"_id": oi["product_id"]})
            if p:
                line_items.append({
                    "quantity": oi["quantity"],
                    "name": p["name"],
                    "image_url": p["image_url"]
                })
        vo["line_items"] = line_items
        
    return render_template("tracking.html", group=group, vendor_orders=vendor_orders_list)

# ── Profile ───────────────────────────────────────────────────────────────────

@app.route("/profile")
@login_required
def profile():
    db = get_db()
    user = db.users.find_one({"_id": session["user_id"]})
    if user: user["id"] = user["_id"]
    return render_template("profile.html", user=user)

@app.route("/profile/update", methods=["POST"])
@login_required
def update_profile():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    db = get_db()
    db.users.update_one(
        {"_id": session["user_id"]},
        {"$set": {"name": name, "phone": phone, "address": address}}
    )
    session["user_name"] = name
    return redirect(url_for("profile"))

@app.route("/profile/change-password", methods=["POST"])
@login_required
def change_password():
    current = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    db = get_db()
    user = db.users.find_one({"_id": session["user_id"]})
    if not check_password_hash(user.get("password_hash", ""), current):
        return redirect(url_for("profile") + "?error=wrong_password")
    db.users.update_one(
        {"_id": session["user_id"]},
        {"$set": {"password_hash": generate_password_hash(new_pw)}}
    )
    return redirect(url_for("profile") + "?success=password_changed")

# ── Wishlist ──────────────────────────────────────────────────────────────────

@app.route("/wishlist")
@login_required
def wishlist():
    db = get_db()
    wish_items = list(db.wishlist.find({"user_id": session["user_id"]}))
    product_ids = [w["product_id"] for w in wish_items]
    products = []
    for pid in product_ids:
        p = db.products.find_one({"_id": pid})
        if p:
            p["id"] = p["_id"]
            products.append(p)
    return render_template("wishlist.html", products=products)

@app.route("/api/wishlist/toggle", methods=["POST"])
@login_required
def toggle_wishlist():
    data = request.get_json()
    product_id = data.get("product_id")
    if not product_id:
        return jsonify({"error": "Missing product_id"}), 400
    db = get_db()
    existing = db.wishlist.find_one({"user_id": session["user_id"], "product_id": product_id})
    if existing:
        db.wishlist.delete_one({"_id": existing["_id"]})
        wishlisted = False
    else:
        db.wishlist.insert_one({"user_id": session["user_id"], "product_id": product_id,
                                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        wishlisted = True
    count = db.wishlist.count_documents({"user_id": session["user_id"]})
    return jsonify({"success": True, "wishlisted": wishlisted, "count": count})

@app.route("/api/wishlist/status")
@login_required
def wishlist_status():
    db = get_db()
    wish_items = db.wishlist.find({"user_id": session["user_id"]})
    ids = [w["product_id"] for w in wish_items]
    count = db.wishlist.count_documents({"user_id": session["user_id"]})
    return jsonify({"wishlisted_ids": ids, "count": count})

# ── Search Autocomplete API ───────────────────────────────────────────────────

@app.route("/api/search/autocomplete")
def search_autocomplete():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    db = get_db()
    regex = {"$regex": f"^{re.escape(q)}", "$options": "i"}
    results = list(db.products.find(
        {"is_approved": 1, "$or": [{"name": regex}, {"brand": regex}, {"category": regex}]},
        {"name": 1, "brand": 1, "category": 1, "price": 1, "image_url": 1}
    ).limit(6))
    suggestions = []
    for r in results:
        suggestions.append({
            "id": r["_id"],
            "name": r["name"],
            "brand": r.get("brand", ""),
            "category": r.get("category", ""),
            "price": r.get("price", 0),
            "image_url": r.get("image_url", "")
        })
    return jsonify(suggestions)

# ── Help & Static ─────────────────────────────────────────────────────────────

@app.route("/help")
def help_center():
    return render_template("help.html")

@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.svg", mimetype="image/svg+xml")

@app.route("/vendor/login", methods=["GET", "POST"])
def vendor_login():
    if "user_id" in session:
        role = session.get("user_role", "customer")
        if role == "vendor":
            return redirect(url_for("vendor_dashboard"))
        elif role == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()
        user = db.users.find_one({"email": email})
        if not user:
            error = "No vendor account found with that email."
        elif user.get("role") not in ("vendor", "admin"):
            error = "This account does not have vendor access. Use the customer login."
        elif user.get("is_blocked"):
            error = "Your account has been suspended. Contact support."
        elif not check_password_hash(user.get("password_hash", ""), password):
            error = "Incorrect password."
        else:
            set_session_from_user(user)
            if user.get("role") == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("vendor_dashboard"))

    return render_template("vendor_login.html", error=error)

# ═════════════════════════════════════════════════════════════════════════════
#  VENDOR DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/vendor")
@vendor_required
def vendor_dashboard():
    uid = session["user_id"]
    db = get_db()
    
    total_products = db.products.count_documents({"vendor_id": uid})
    
    # Orders containing vendor's products
    vo_pipeline = [
        {"$match": {"vendor_id": uid}},
        {"$group": {
            "_id": None,
            "cnt": {"$sum": 1},
            "rev": {"$sum": "$subtotal"}
        }}
    ]
    vo_stats = list(db.vendor_orders.aggregate(vo_pipeline))
    
    total_orders = vo_stats[0]["cnt"] if vo_stats else 0
    revenue = vo_stats[0]["rev"] if vo_stats else 0
    
    oi_pipeline = [
        {"$lookup": {"from": "products", "localField": "product_id", "foreignField": "_id", "as": "product"}},
        {"$unwind": "$product"},
        {"$match": {"product.vendor_id": uid}},
        {"$group": {"_id": None, "units": {"$sum": "$quantity"}}}
    ]
    oi_stats = list(db.order_items.aggregate(oi_pipeline))
    total_units_sold = oi_stats[0]["units"] if oi_stats else 0
    
    recent_orders = []
    recent_vo = list(db.vendor_orders.find({"vendor_id": uid}).sort("created_at", -1).limit(5))
    for vo in recent_vo:
        og = db.order_groups.find_one({"_id": vo["order_group_id"]})
        u = db.users.find_one({"_id": og["user_id"]}) if og else None
        
        oi_list = list(db.order_items.find({"vendor_order_id": vo["_id"]}))
        p_names = []
        for oi in oi_list:
            p = db.products.find_one({"_id": oi["product_id"]})
            if p: p_names.append(p["name"])
            
        recent_orders.append({
            "id": og["_id"] if og else 0,
            "total": vo["subtotal"],
            "status": vo["status"],
            "created_at": og["created_at"] if og else vo["created_at"],
            "customer_name": u["name"] if u else "Unknown",
            "product_names": ", ".join(p_names)
        })

    recent_products = list(db.products.find({"vendor_id": uid}).sort("_id", -1).limit(5))
    for p in recent_products: p["id"] = p["_id"]

    top_products_pipeline = [
        {"$lookup": {"from": "products", "localField": "product_id", "foreignField": "_id", "as": "product"}},
        {"$unwind": "$product"},
        {"$match": {"product.vendor_id": uid}},
        {"$group": {
            "_id": "$product_id",
            "name": {"$first": "$product.name"},
            "image_url": {"$first": "$product.image_url"},
            "category": {"$first": "$product.category"},
            "total_sold": {"$sum": "$quantity"},
            "revenue": {"$sum": {"$multiply": ["$quantity", "$price"]}}
        }},
        {"$sort": {"total_sold": -1}},
        {"$limit": 5}
    ]
    top_products = list(db.order_items.aggregate(top_products_pipeline))

    status_pipeline = [
        {"$match": {"vendor_id": uid}},
        {"$group": {"_id": "$status", "cnt": {"$sum": 1}}}
    ]
    status_raw = list(db.vendor_orders.aggregate(status_pipeline))
    all_statuses = ["confirmed", "preparing", "shipped", "delivered", "pending"]
    status_map = {r["_id"].lower(): r["cnt"] for r in status_raw if r["_id"]}
    order_status = [{"status": s.capitalize(), "cnt": status_map.get(s, 0)} for s in all_statuses]

    return render_template("vendor_dashboard.html",
        total_products=total_products,
        total_orders=total_orders,
        total_units_sold=total_units_sold,
        revenue=revenue,
        recent_orders=recent_orders,
        recent_products=recent_products,
        top_products=top_products,
        order_status=order_status,
        active="overview"
    )

@app.route("/vendor/products")
@vendor_required
def vendor_products():
    db = get_db()
    products = list(db.products.find({"vendor_id": session["user_id"]}).sort("_id", -1))
    for p in products: p["id"] = p["_id"]
    return render_template("vendor_dashboard.html", products=products, active="products")

@app.route("/vendor/products/add", methods=["GET", "POST"])
@vendor_required
def vendor_add_product():
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        brand = request.form.get("brand", "").strip()
        category = request.form.get("category", "").strip()
        price = request.form.get("price", "")
        original_price = request.form.get("original_price", "").strip()
        unit = request.form.get("unit", "").strip()
        image_url = request.form.get("image_url", "").strip()
        badge = request.form.get("badge", "").strip()
        stock = request.form.get("stock", "100").strip()

        if not all([name, brand, category, price, unit]):
            error = "Name, brand, category, price and unit are required."
        else:
            try:
                price = float(price)
                stock = int(stock) if stock else 100
                op = float(original_price) if original_price else None
                db = get_db()
                
                last_p = db.products.find_one(sort=[("_id", -1)])
                new_id = (last_p["_id"] + 1) if last_p and isinstance(last_p.get("_id"), int) else 1
                
                db.products.insert_one({
                    "_id": new_id,
                    "name": name,
                    "brand": brand,
                    "category": category,
                    "price": price,
                    "original_price": op,
                    "unit": unit,
                    "image_url": image_url or "https://via.placeholder.com/400x400?text=Product",
                    "badge": badge or None,
                    "vendor_id": session["user_id"],
                    "is_approved": 1,
                    "stock": stock
                })
                return redirect(url_for("vendor_products"))
            except ValueError:
                error = "Invalid price or stock value."

    categories = ["Fresh Produce", "Dairy & Eggs", "Bakery", "Meat & Seafood", "Pantry Staples", "Beverages", "Snacks"]
    return render_template("vendor_dashboard.html",
        active="add_product", error=error, categories=categories
    )

@app.route("/vendor/products/edit/<int:pid>", methods=["GET", "POST"])
@vendor_required
def vendor_edit_product(pid):
    db = get_db()
    product = db.products.find_one({"_id": pid, "vendor_id": session["user_id"]})
    if not product:
        return redirect(url_for("vendor_products"))
    product["id"] = product["_id"]

    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        brand = request.form.get("brand", "").strip()
        category = request.form.get("category", "").strip()
        price = request.form.get("price", "")
        original_price = request.form.get("original_price", "").strip()
        unit = request.form.get("unit", "").strip()
        image_url = request.form.get("image_url", "").strip()
        badge = request.form.get("badge", "").strip()
        stock = request.form.get("stock", "100").strip()

        if not all([name, brand, category, price, unit]):
            error = "All required fields must be filled."
        else:
            try:
                price = float(price)
                stock = int(stock) if stock else 100
                op = float(original_price) if original_price else None
                db.products.update_one(
                    {"_id": pid, "vendor_id": session["user_id"]},
                    {"$set": {
                        "name": name, "brand": brand, "category": category,
                        "price": price, "original_price": op, "unit": unit,
                        "image_url": image_url, "badge": badge or None, "stock": stock
                    }}
                )
                return redirect(url_for("vendor_products"))
            except ValueError:
                error = "Invalid price or stock value."

    categories = ["Fresh Produce", "Dairy & Eggs", "Bakery", "Meat & Seafood", "Pantry Staples", "Beverages", "Snacks"]
    return render_template("vendor_dashboard.html",
        active="edit_product", product=product, error=error, categories=categories
    )

@app.route("/vendor/products/delete/<int:pid>", methods=["POST"])
@vendor_required
def vendor_delete_product(pid):
    db = get_db()
    db.products.delete_one({"_id": pid, "vendor_id": session["user_id"]})
    return redirect(url_for("vendor_products"))

@app.route("/vendor/orders")
@vendor_required
def vendor_orders():
    db = get_db()
    uid = session["user_id"]
    orders = []
    vo_list = list(db.vendor_orders.find({"vendor_id": uid}).sort("created_at", -1))
    
    for vo in vo_list:
        og = db.order_groups.find_one({"_id": vo["order_group_id"]})
        u = db.users.find_one({"_id": og["user_id"]}) if og else None
        
        oi_list = list(db.order_items.find({"vendor_order_id": vo["_id"]}))
        line_items = []
        for oi in oi_list:
            p = db.products.find_one({"_id": oi["product_id"]})
            if p:
                line_items.append({
                    "quantity": oi["quantity"],
                    "price": oi["price"],
                    "name": p["name"],
                    "image_url": p["image_url"]
                })
                
        orders.append({
            "id": vo["_id"],
            "order_group_id": vo["order_group_id"],
            "subtotal": vo["subtotal"],
            "status": vo["status"],
            "created_at": vo["created_at"],
            "address": og["address"] if og else "",
            "pincode": og["pincode"] if og else "",
            "mobile": og["mobile"] if og else "",
            "customer_name": u["name"] if u else "Unknown",
            "customer_email": u["email"] if u else "Unknown",
            "line_items": line_items
        })
        
    return render_template("vendor_dashboard.html", orders=orders, active="orders")

@app.route("/vendor/orders/<int:oid>/status", methods=["POST"])
@vendor_required
def vendor_update_order_status(oid):
    status = request.form.get("status", "pending")
    allowed = ["pending", "confirmed", "shipped", "delivered"]
    if status in allowed:
        db = get_db()
        db.vendor_orders.update_one(
            {"_id": oid, "vendor_id": session["user_id"]},
            {"$set": {"status": status}}
        )
    return redirect(url_for("vendor_orders"))

# ═════════════════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    total_customers = db.users.count_documents({"role": "customer"})
    total_vendors = db.users.count_documents({"role": "vendor"})
    total_products = db.products.count_documents({})
    total_orders = db.order_groups.count_documents({})
    
    rev_pipeline = [{"$group": {"_id": None, "rev": {"$sum": "$total_amount"}}}]
    rev_res = list(db.order_groups.aggregate(rev_pipeline))
    total_revenue = rev_res[0]["rev"] if rev_res else 0
    pending_products = db.products.count_documents({"is_approved": 0})

    recent_orders = []
    og_list = list(db.order_groups.find().sort("created_at", -1).limit(8))
    for og in og_list:
        u = db.users.find_one({"_id": og["user_id"]})
        vo_count = db.vendor_orders.count_documents({"order_group_id": og["_id"]})
        del_count = db.vendor_orders.count_documents({"order_group_id": og["_id"], "status": "delivered"})
        
        status = "pending"
        if vo_count > 0:
            if del_count == vo_count:
                status = "delivered"
            else:
                status = "in progress"
                
        recent_orders.append({
            "id": og["_id"],
            "total": og["total_amount"],
            "created_at": og["created_at"],
            "customer_name": u["name"] if u else "Unknown",
            "status": status
        })

    recent_users = list(db.users.find().sort("created_at", -1).limit(8))
    for u in recent_users: u["id"] = u["_id"]

    top_products_pipeline = [
        {"$lookup": {"from": "products", "localField": "product_id", "foreignField": "_id", "as": "product"}},
        {"$unwind": "$product"},
        {"$group": {
            "_id": "$product_id",
            "name": {"$first": "$product.name"},
            "image_url": {"$first": "$product.image_url"},
            "category": {"$first": "$product.category"},
            "total_sold": {"$sum": "$quantity"},
            "revenue": {"$sum": {"$multiply": ["$quantity", "$price"]}}
        }},
        {"$sort": {"total_sold": -1}},
        {"$limit": 5}
    ]
    top_products = list(db.order_items.aggregate(top_products_pipeline))

    # Simplified top vendors
    top_vendors = []
    vendors = list(db.users.find({"role": "vendor"}))
    for v in vendors:
        v_pipeline = [
            {"$match": {"vendor_id": v["_id"]}},
            {"$group": {"_id": None, "rev": {"$sum": "$subtotal"}}}
        ]
        res = list(db.vendor_orders.aggregate(v_pipeline))
        rev = res[0]["rev"] if res else 0
        p_count = db.products.count_documents({"vendor_id": v["_id"]})
        o_count = db.vendor_orders.count_documents({"vendor_id": v["_id"]})
        top_vendors.append({
            "id": v["_id"],
            "name": v["name"],
            "email": v["email"],
            "product_count": p_count,
            "order_count": o_count,
            "revenue": rev
        })
    top_vendors.sort(key=lambda x: x["revenue"], reverse=True)
    top_vendors = top_vendors[:5]

    return render_template("admin_dashboard.html",
        total_customers=total_customers,
        total_vendors=total_vendors,
        total_products=total_products,
        total_orders=total_orders,
        total_revenue=total_revenue,
        pending_products=pending_products,
        recent_orders=recent_orders,
        recent_users=recent_users,
        top_products=top_products,
        top_vendors=top_vendors,
        active="overview"
    )

@app.route("/admin/users")
@admin_required
def admin_users():
    db = get_db()
    search = request.args.get("search", "").strip()
    role_filter = request.args.get("role", "")

    query = {}
    if search:
        regex = {"$regex": search, "$options": "i"}
        query["$or"] = [{"name": regex}, {"email": regex}]
    if role_filter:
        query["role"] = role_filter

    users = list(db.users.find(query).sort("created_at", -1))
    for u in users: u["id"] = u["_id"]
    return render_template("admin_dashboard.html",
        users=users, search=search, role_filter=role_filter, active="users"
    )

@app.route("/admin/users/<int:uid>/role", methods=["POST"])
@admin_required
def admin_set_role(uid):
    role = request.form.get("role", "customer")
    if uid == session["user_id"]: return redirect(url_for("admin_users"))
    if role in ("customer", "vendor", "admin"):
        db = get_db()
        db.users.update_one({"_id": uid}, {"$set": {"role": role}})
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:uid>/block", methods=["POST"])
@admin_required
def admin_toggle_block(uid):
    if uid == session["user_id"]: return redirect(url_for("admin_users"))
    db = get_db()
    user = db.users.find_one({"_id": uid})
    if user:
        new_status = 0 if user.get("is_blocked") else 1
        db.users.update_one({"_id": uid}, {"$set": {"is_blocked": new_status}})
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:uid>/delete", methods=["POST"])
@admin_required
def admin_delete_user(uid):
    if uid == session["user_id"]: return redirect(url_for("admin_users"))
    db = get_db()
    db.users.delete_one({"_id": uid})
    return redirect(url_for("admin_users"))

@app.route("/admin/products")
@admin_required
def admin_products():
    db = get_db()
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "")

    query = {}
    if search:
        regex = {"$regex": search, "$options": "i"}
        query["$or"] = [{"name": regex}, {"brand": regex}]
    if status_filter == "pending": query["is_approved"] = 0
    elif status_filter == "approved": query["is_approved"] = 1

    products = list(db.products.find(query).sort("_id", -1))
    for p in products:
        p["id"] = p["_id"]
        v = db.users.find_one({"_id": p.get("vendor_id")})
        p["vendor_name"] = v["name"] if v else "Unknown"

    return render_template("admin_dashboard.html",
        products=products, search=search, status_filter=status_filter, active="products"
    )

@app.route("/admin/products/<int:pid>/approve", methods=["POST"])
@admin_required
def admin_approve_product(pid):
    db = get_db()
    p = db.products.find_one({"_id": pid})
    if p:
        db.products.update_one({"_id": pid}, {"$set": {"is_approved": 0 if p.get("is_approved") else 1}})
    return redirect(url_for("admin_products"))

@app.route("/admin/products/<int:pid>/delete", methods=["POST"])
@admin_required
def admin_delete_product(pid):
    db = get_db()
    db.products.delete_one({"_id": pid})
    return redirect(url_for("admin_products"))

@app.route("/admin/orders")
@admin_required
def admin_orders():
    db = get_db()
    status_filter = request.args.get("status", "")

    query = {}
    if status_filter:
        vo_list = list(db.vendor_orders.find({"status": status_filter}))
        og_ids = [vo["order_group_id"] for vo in vo_list]
        query["_id"] = {"$in": og_ids}

    og_list = list(db.order_groups.find(query).sort("created_at", -1))
    groups = []
    
    for og in og_list:
        u = db.users.find_one({"_id": og["user_id"]})
        vo_list = list(db.vendor_orders.find({"order_group_id": og["_id"]}))
        for vo in vo_list: vo["id"] = vo["_id"]
        
        statuses = [vo["status"] for vo in vo_list]
        overall_status = "pending"
        if statuses:
            if all(s == "delivered" for s in statuses): overall_status = "delivered"
            elif any(s == "shipped" for s in statuses): overall_status = "in transit"
            elif any(s == "confirmed" for s in statuses): overall_status = "confirmed"

        groups.append({
            "id": og["_id"],
            "total_amount": og["total_amount"],
            "address": og["address"],
            "created_at": og["created_at"],
            "customer_name": u["name"] if u else "Unknown",
            "customer_email": u["email"] if u else "Unknown",
            "vendor_orders": vo_list,
            "overall_status": overall_status
        })

    return render_template("admin_dashboard.html",
        orders=groups, status_filter=status_filter, active="orders"
    )

@app.route("/admin/orders/<int:oid>/status", methods=["POST"])
@admin_required
def admin_update_order(oid):
    status = request.form.get("status", "pending")
    allowed = ["pending", "confirmed", "shipped", "delivered"]
    if status in allowed:
        db = get_db()
        db.vendor_orders.update_one({"_id": oid}, {"$set": {"status": status}})
    return redirect(url_for("admin_orders"))

# ── Admin Export APIs ────────────────────────────────────────────────────────

@app.route("/admin/export/orders")
@admin_required
def admin_export_orders():
    db = get_db()
    og_list = list(db.order_groups.find().sort("created_at", -1))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Order ID", "Customer Name", "Customer Email", "Address", "Pincode", "Mobile",
                     "Total Amount", "Tax", "Delivery Fee", "Date", "Overall Status"])
    for og in og_list:
        u = db.users.find_one({"_id": og["user_id"]})
        vo_list = list(db.vendor_orders.find({"order_group_id": og["_id"]}))
        statuses = [vo["status"] for vo in vo_list]
        overall = "pending"
        if statuses:
            if all(s == "delivered" for s in statuses): overall = "delivered"
            elif any(s == "shipped" for s in statuses): overall = "in transit"
            elif any(s == "confirmed" for s in statuses): overall = "confirmed"
        writer.writerow([
            og["_id"],
            u["name"] if u else "Unknown",
            u["email"] if u else "Unknown",
            og.get("address", ""),
            og.get("pincode", ""),
            og.get("mobile", ""),
            f"${og.get('total_amount', 0):.2f}",
            f"${og.get('tax', 0):.2f}",
            f"${og.get('delivery_fee', 0):.2f}",
            og.get("created_at", ""),
            overall
        ])
    output.seek(0)
    filename = f"orders_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename={filename}"})

@app.route("/admin/export/revenue")
@admin_required
def admin_export_revenue():
    db = get_db()
    pipeline = [
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 10]},
            "orders": {"$sum": 1},
            "revenue": {"$sum": "$total_amount"},
            "tax": {"$sum": "$tax"},
            "delivery": {"$sum": "$delivery_fee"}
        }},
        {"$sort": {"_id": 1}}
    ]
    rows = list(db.order_groups.aggregate(pipeline))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Orders Count", "Revenue", "Tax Collected", "Delivery Fees"])
    for r in rows:
        writer.writerow([
            r["_id"],
            r["orders"],
            f"${r['revenue']:.2f}",
            f"${r['tax']:.2f}",
            f"${r['delivery']:.2f}"
        ])
    output.seek(0)
    filename = f"revenue_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename={filename}"})

# ── Support API ───────────────────────────────────────────────────────────────

@app.route("/api/support/email", methods=["POST"])
def support_email():
    data = request.get_json()
    print(f"\n--- MOCK EMAIL SENT ---")
    print(f"From: {session.get('user_email', 'Guest')}")
    print(f"To: support@smartgrocery.com")
    print(f"Subject: {data.get('subject')}")
    print(f"Message: {data.get('message')}")
    print(f"-----------------------\n")
    return jsonify({"success": True})

@app.route("/api/chat", methods=["POST"])
def chat():
    if "user_id" not in session:
        return jsonify({"response": "Please log in to use the AI support chat. Your account context is needed so I can check your specific orders!"}), 401
    
    data = request.get_json()
    user_message = data.get("message", "").strip()
    
    order_context = ""
    order_match = re.search(r'(?:order(?: id)?|#)\s*(\d+)', user_message.lower())
    
    if order_match:
        order_id = int(order_match.group(1))
        db = get_db()
        group = db.order_groups.find_one({"_id": order_id, "user_id": session["user_id"]})
        if group:
            vo_list = list(db.vendor_orders.find({"order_group_id": order_id}))
            statuses = [vo["status"] for vo in vo_list]
            overall_status = "pending"
            if statuses:
                if all(s == "delivered" for s in statuses): overall_status = "delivered"
                elif any(s == "shipped" for s in statuses): overall_status = "shipped"
                elif any(s == "confirmed" for s in statuses): overall_status = "confirmed"
                
            order_context = f"\n\n[SYSTEM CONTEXT: The user is asking about Order ID {order_id}. The database confirms this order exists and its current status is '{overall_status}'. The order total was ${group.get('total_amount',0)}. Address is {group.get('address','')}. Use this verified DB data to answer the user's question accurately.]"
        else:
            order_context = f"\n\n[SYSTEM CONTEXT: The user asked about Order ID {order_id}, but this order ID does NOT exist in their account. Apologize and say you cannot find that order in their history.]"

    system_prompt = """You are the 'Smart Grocery AI', a helpful, polite customer support assistant for a grocery delivery service.
Rules:
1. ONLY answer questions related to the grocery store, orders, grocery products, and support topics.
2. If the user asks about ANYTHING else (math, coding, write a poem, general trivia, unrelated topics), politely decline to answer, stating you are just a grocery assistant.
3. You have read-only access to order status. If SYSTEM CONTEXT is provided, use it factually to help the user. Do not make up statuses.
4. Keep your responses friendly but concise (1-3 sentences maximum)."""

    prompt = f"{system_prompt}{order_context}\n\nUser: {user_message}\nAI Assistant:"

    try:
        response = requests.post('http://127.0.0.1:11434/api/generate', json={
            "model": "llama3:latest",
            "prompt": prompt,
            "stream": False
        }, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            return jsonify({"response": result.get("response", "Sorry, I am having trouble forming a response right now.")})
        else:
            return jsonify({"response": "I'm sorry, our AI service is currently having trouble processing requests. Please call or email us instead."})
            
    except requests.exceptions.RequestException as e:
        print("LLaMA Error:", e)
        return jsonify({"response": "I'm sorry, my AI backend is offline right now. Please ensure Ollama is running locally."})

# ── Password Recovery ─────────────────────────────────────────────────────────

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    error = None
    success = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        db = get_db()
        user = db.users.find_one({"email": email})
        if user:
            token = secrets.token_urlsafe(32)
            expiry = datetime.datetime.now() + timedelta(hours=1)
            db.users.update_one({"_id": user["_id"]}, {"$set": {"reset_token": token, "reset_expiry": expiry}})
            reset_url = url_for("reset_password", token=token, _external=True)
            print("\n" + "="*50)
            print("MOCK EMAIL NOTIFICATION")
            print(f"To: {email}")
            print(f"Subject: Password Reset Request")
            print(f"Please click the link below to reset your password:\n{reset_url}")
            print("="*50 + "\n")
            success = "If your email exists in our system, you will receive a reset link shortly."
        else:
            success = "If your email exists in our system, you will receive a reset link shortly."
    return render_template("forgot_password.html", error=error, success=success)

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    db = get_db()
    user = db.users.find_one({"reset_token": token})
    
    if not user or (user.get("reset_expiry") and datetime.datetime.now() > user["reset_expiry"]):
        return render_template("reset_password.html", error="Invalid or expired reset token.")
        
    if request.method == "POST":
        new_pw = request.form.get("password", "")
        if len(new_pw) < 6:
            return render_template("reset_password.html", error="Password must be at least 6 characters.", token=token)
            
        db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"password_hash": generate_password_hash(new_pw)}, "$unset": {"reset_token": "", "reset_expiry": ""}}
        )
        return redirect(url_for("login", msg="password_reset_success"))
        
    return render_template("reset_password.html", token=token)

# ── Chart APIs ────────────────────────────────────────────────────────────────

@app.route("/api/admin/chart-data")
@admin_required
def admin_chart_data():
    filter_type = request.args.get("filter", "7d")
    db = get_db()
    now = datetime.datetime.now()
    
    if filter_type == "7d":
        start_date = now - timedelta(days=7)
        fmt = "%b %d"
    elif filter_type == "1m":
        start_date = now - timedelta(days=30)
        fmt = "%b %d"
    elif filter_type == "1y":
        start_date = now - timedelta(days=365)
        fmt = "%b %Y"
    else:
        start_date = now - timedelta(days=7)
        fmt = "%b %d"
        
    start_date_str = start_date.strftime("%Y-%m-%d 00:00:00")
    
    pipeline = [
        {"$match": {"created_at": {"$gte": start_date_str}}},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 10 if filter_type != "1y" else 7]},
            "revenue": {"$sum": "$total_amount"},
            "orders": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    res = list(db.order_groups.aggregate(pipeline))
    
    labels = []
    revenue = []
    orders = []
    
    for r in res:
        d_str = r["_id"]
        if len(d_str) == 10:
            d_obj = datetime.datetime.strptime(d_str, "%Y-%m-%d")
        else:
            d_obj = datetime.datetime.strptime(d_str, "%Y-%m")
        labels.append(d_obj.strftime(fmt))
        revenue.append(r["revenue"])
        orders.append(r["orders"])
        
    return jsonify({"labels": labels, "revenue": revenue, "orders": orders})

@app.route("/api/vendor/chart-data")
@vendor_required
def vendor_chart_data():
    filter_type = request.args.get("filter", "7d")
    uid = session["user_id"]
    db = get_db()
    now = datetime.datetime.now()
    
    if filter_type == "7d":
        start_date = now - timedelta(days=7)
        fmt = "%b %d"
    elif filter_type == "1m":
        start_date = now - timedelta(days=30)
        fmt = "%b %d"
    elif filter_type == "1y":
        start_date = now - timedelta(days=365)
        fmt = "%b %Y"
    else:
        start_date = now - timedelta(days=7)
        fmt = "%b %d"
        
    start_date_str = start_date.strftime("%Y-%m-%d 00:00:00")
    
    pipeline = [
        {"$match": {"vendor_id": uid, "created_at": {"$gte": start_date_str}}},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 10 if filter_type != "1y" else 7]},
            "revenue": {"$sum": "$subtotal"}
        }},
        {"$sort": {"_id": 1}}
    ]
    res = list(db.vendor_orders.aggregate(pipeline))
    
    labels = []
    revenue = []
    
    for r in res:
        d_str = r["_id"]
        if len(d_str) == 10:
            d_obj = datetime.datetime.strptime(d_str, "%Y-%m-%d")
        else:
            d_obj = datetime.datetime.strptime(d_str, "%Y-%m")
        labels.append(d_obj.strftime(fmt))
        revenue.append(r["revenue"])
        
    return jsonify({"labels": labels, "revenue": revenue})

# ── Setup admin on first run ──────────────────────────────────────────────────

def ensure_demo_accounts():
    db = get_db()
    admin = db.users.find_one({"email": "admin@smartgrocery.com"})
    if not admin:
        last_u = db.users.find_one(sort=[("_id", -1)])
        new_id = (last_u["_id"] + 1) if last_u and isinstance(last_u.get("_id"), int) else 1
        db.users.insert_one({
            "_id": new_id,
            "name": "Admin",
            "email": "admin@smartgrocery.com",
            "password_hash": generate_password_hash("admin123"),
            "role": "admin",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    else:
        db.users.update_one({"_id": admin["_id"]}, {"$set": {"role": "admin"}})

    vendor = db.users.find_one({"email": "vendor@smartgrocery.com"})
    if not vendor:
        last_u = db.users.find_one(sort=[("_id", -1)])
        new_id = (last_u["_id"] + 1) if last_u and isinstance(last_u.get("_id"), int) else 1
        db.users.insert_one({
            "_id": new_id,
            "name": "Demo Vendor",
            "email": "vendor@smartgrocery.com",
            "password_hash": generate_password_hash("vendor123"),
            "role": "vendor",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    else:
        db.users.update_one({"_id": vendor["_id"]}, {"$set": {"role": "vendor"}})

if __name__ == "__main__":
    init_db()
    ensure_demo_accounts()
    app.run(host="0.0.0.0", port=5000, debug=True)
