from database import get_db
from collections import defaultdict

def _fetch_user_purchase_profile(db, user_id):
    pipeline = [
        {"$lookup": {
            "from": "order_groups",
            "localField": "order_id",
            "foreignField": "_id",
            "as": "order"
        }},
        {"$unwind": "$order"},
        {"$match": {"order.user_id": user_id}},
        {"$group": {
            "_id": "$product_id",
            "total_qty": {"$sum": "$quantity"},
            "orders": {"$addToSet": "$order_id"},
            "last_ordered": {"$max": "$order.created_at"}
        }},
        {"$project": {
            "product_id": "$_id",
            "total_qty": 1,
            "order_freq": {"$size": "$orders"},
            "last_ordered": 1
        }},
        {"$sort": {"total_qty": -1}}
    ]
    rows = list(db.order_items.aggregate(pipeline))
    if not rows:
        return {}

    max_qty = max(r["total_qty"] for r in rows) if rows else 1

    profile = {}
    for r in rows:
        freq_score = r["total_qty"] / max_qty
        recency_bonus = 0.2 if r["last_ordered"] else 0
        profile[r["product_id"]] = round(freq_score + recency_bonus, 4)

    return profile

def _fetch_top_categories(db, profile, top_n=3):
    if not profile:
        return []
    ids = list(profile.keys())
    products = list(db.products.find({"_id": {"$in": ids}}))
    cat_scores = defaultdict(float)
    for p in products:
        cat_scores[p.get("category", "")] += profile.get(p["_id"], 0)
    return sorted(cat_scores, key=lambda k: -cat_scores[k])[:top_n]

def _fetch_products_by_ids(db, ids):
    if not ids:
        return []
    products = list(db.products.find({"_id": {"$in": ids}}))
    by_id = {p["_id"]: p for p in products}
    return [by_id[i] for i in ids if i in by_id]

def get_recommendations(user_id, limit=6):
    db = get_db()
    profile = _fetch_user_purchase_profile(db, user_id)
    cart_items = list(db.cart.find({"user_id": user_id}))
    cart_ids = {item["product_id"] for item in cart_items}

    scored = {}

    pipeline = [
        {"$lookup": {"from": "order_groups", "localField": "order_id", "foreignField": "_id", "as": "order"}},
        {"$unwind": "$order"},
        {"$match": {"order.user_id": user_id}},
        {"$group": {
            "_id": "$product_id",
            "total_qty": {"$sum": "$quantity"},
            "orders": {"$addToSet": "$order_id"},
            "last_ordered": {"$max": "$order.created_at"}
        }}
    ]
    purchase_rows = list(db.order_items.aggregate(pipeline))
    
    if purchase_rows:
        purchase_rows.sort(key=lambda x: x["last_ordered"] or "", reverse=True)
        for rank, r in enumerate(purchase_rows):
            r["recency_rank"] = rank + 1
            r["order_freq"] = len(r["orders"])
            r["product_id"] = r["_id"]

        for r in purchase_rows:
            pid = r["product_id"]
            freq_score = r["total_qty"] * 1.5 + r["order_freq"] * 2.0
            recency_boost = 3.0 if r["recency_rank"] <= 3 else 0
            final_score = freq_score + recency_boost

            if r["total_qty"] >= 3 or r["order_freq"] >= 2:
                reason = "You order this often"
            elif r["recency_rank"] <= 3:
                reason = "Recently purchased"
            else:
                reason = "In your history"

            if pid not in scored or scored[pid][0] < final_score:
                scored[pid] = (final_score, reason)

    top_cats = _fetch_top_categories(db, profile)
    if top_cats:
        bought_ids = list(profile.keys())
        for cat in top_cats:
            cat_prods = list(db.products.find({"category": cat, "_id": {"$nin": bought_ids}}))
            for p in cat_prods:
                pid = p["_id"]
                cat_score = 1.5
                if pid not in scored or scored[pid][0] < cat_score:
                    scored[pid] = (cat_score, f"Similar to your {cat} picks")

    if profile:
        bought_ids = list(profile.keys())
        pipeline_collab = [
            {"$match": {"product_id": {"$in": bought_ids}}},
            {"$lookup": {"from": "order_groups", "localField": "order_id", "foreignField": "_id", "as": "o1"}},
            {"$unwind": "$o1"},
            {"$match": {"o1.user_id": user_id}},
            {"$lookup": {"from": "order_groups", "localField": "o1._id", "foreignField": "id", "as": "o2_fake"}}, 
            # Very hard to do this exact collab query in Mongo purely. 
            # Let's approximate: Find other users who bought these products
        ]
        
        # Simplified collab filtering
        other_orders_pipeline = [
            {"$match": {"product_id": {"$in": bought_ids}}},
            {"$lookup": {"from": "order_groups", "localField": "order_id", "foreignField": "_id", "as": "order"}},
            {"$unwind": "$order"},
            {"$match": {"order.user_id": {"$ne": user_id}}},
            {"$group": {"_id": "$order.user_id"}}
        ]
        other_users = [u["_id"] for u in db.order_items.aggregate(other_orders_pipeline)]
        
        if other_users:
            collab_prods = list(db.order_items.aggregate([
                {"$lookup": {"from": "order_groups", "localField": "order_id", "foreignField": "_id", "as": "order"}},
                {"$unwind": "$order"},
                {"$match": {"order.user_id": {"$in": other_users}, "product_id": {"$nin": bought_ids}}},
                {"$group": {"_id": "$product_id", "user_count": {"$addToSet": "$order.user_id"}, "collab_qty": {"$sum": "$quantity"}}},
                {"$project": {"user_count": {"$size": "$user_count"}, "collab_qty": 1}},
                {"$sort": {"user_count": -1, "collab_qty": -1}},
                {"$limit": limit * 3}
            ]))
            for r in collab_prods:
                pid = r["_id"]
                collab_score = r["user_count"] * 1.2
                if pid not in scored or scored[pid][0] < collab_score:
                    scored[pid] = (collab_score, "Others like you also buy this")

    excluded = set(scored.keys()) | cart_ids
    if len(scored) < limit:
        pop_pipeline = [
            {"$match": {"product_id": {"$nin": list(excluded)}}},
            {"$group": {"_id": "$product_id", "pop": {"$sum": "$quantity"}}},
            {"$sort": {"pop": -1}},
            {"$limit": limit}
        ]
        popular_items = list(db.order_items.aggregate(pop_pipeline))
        for r in popular_items:
            pid = r["_id"]
            if pid not in scored:
                scored[pid] = (0.5, "Popular this week")

        if len(scored) < limit:
            remaining = limit - len(scored)
            extra_prods = list(db.products.find({"_id": {"$nin": list(excluded)}}).limit(remaining))
            for p in extra_prods:
                if p["_id"] not in scored:
                    scored[p["_id"]] = (0.1, "Recommended for you")

    for cid in cart_ids:
        scored.pop(cid, None)

    ranked = sorted(scored.items(), key=lambda x: -x[1][0])
    top_ids = [pid for pid, _ in ranked[:limit]]
    reasons = {pid: info[1] for pid, info in ranked[:limit]}

    products = _fetch_products_by_ids(db, top_ids)
    for p in products:
        p["reason"] = reasons.get(p["_id"], "Recommended for you")
        p["id"] = p["_id"] # Make sure frontend still gets 'id'

    return products

def get_popular_products(limit=6):
    db = get_db()
    pipeline = [
        {"$group": {"_id": "$product_id", "order_count": {"$sum": "$quantity"}}},
        {"$sort": {"order_count": -1}},
        {"$limit": limit}
    ]
    popular = list(db.order_items.aggregate(pipeline))
    pop_ids = [p["_id"] for p in popular]
    
    products = list(db.products.find({"_id": {"$in": pop_ids}}))
    if len(products) < limit:
        extra_prods = list(db.products.find({"_id": {"$nin": pop_ids}}).limit(limit - len(products)))
        products.extend(extra_prods)
        
    for p in products:
        p["reason"] = "Popular this week"
        p["id"] = p["_id"]
    return products

def get_user_purchase_summary(user_id):
    db = get_db()
    
    pipeline_totals = [
        {"$match": {"user_id": user_id}},
        {"$lookup": {"from": "order_items", "localField": "_id", "foreignField": "order_id", "as": "items"}},
        {"$project": {
            "items_bought": {"$sum": "$items.quantity"}
        }}
    ]
    orders = list(db.order_groups.aggregate(pipeline_totals))
    order_count = len(orders)
    items_bought = sum(o.get("items_bought", 0) for o in orders)

    pipeline_cats = [
        {"$lookup": {"from": "order_groups", "localField": "order_id", "foreignField": "_id", "as": "order"}},
        {"$unwind": "$order"},
        {"$match": {"order.user_id": user_id}},
        {"$lookup": {"from": "products", "localField": "product_id", "foreignField": "_id", "as": "product"}},
        {"$unwind": "$product"},
        {"$group": {"_id": "$product.category", "qty": {"$sum": "$quantity"}}},
        {"$sort": {"qty": -1}},
        {"$limit": 3}
    ]
    cats = list(db.order_items.aggregate(pipeline_cats))
    top_cats = [c["_id"] for c in cats]

    return {
        "order_count": order_count,
        "items_bought": items_bought,
        "top_categories": top_cats,
    }
