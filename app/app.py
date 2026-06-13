import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone

from flask import Flask, Response, g, jsonify, render_template_string, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from werkzeug.exceptions import HTTPException


APP_NAME = "ShopEase API"
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_ENV = os.getenv("APP_ENV", "development")
APP_CURRENCY = "INR"
PORT = int(os.getenv("PORT", "5000"))
START_TIME = time.monotonic()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("shopease")

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

REQUESTS_TOTAL = Counter(
    "shopease_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "shopease_request_latency_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
)
ACTIVE_REQUESTS = Gauge(
    "shopease_active_requests",
    "Number of HTTP requests currently being processed",
)
APP_HEALTH = Gauge(
    "shopease_app_health",
    "Application health status: 1=healthy, 0=unhealthy",
)
ORDERS_TOTAL = Counter("shopease_orders_total", "Total orders created")
PRODUCTS_VIEWED_TOTAL = Counter(
    "shopease_products_viewed_total",
    "Total individual product views",
    ["product"],
)
APP_HEALTH.set(1)

PRODUCTS = [
    {"id": 1, "name": "Wireless Headphones", "price": 6499, "category": "Electronics", "stock": 25},
    {"id": 2, "name": "Mechanical Keyboard", "price": 8999, "category": "Electronics", "stock": 18},
    {"id": 3, "name": "Running Shoes", "price": 7499, "category": "Footwear", "stock": 32},
    {"id": 4, "name": "Stainless Steel Bottle", "price": 1999, "category": "Home", "stock": 60},
    {"id": 5, "name": "Laptop Backpack", "price": 4499, "category": "Accessories", "stock": 20},
    {"id": 6, "name": "Smart Watch", "price": 16999, "category": "Electronics", "stock": 12},
    {"id": 7, "name": "Cotton Hoodie", "price": 3999, "category": "Clothing", "stock": 40},
    {"id": 8, "name": "Desk Lamp", "price": 2999, "category": "Home", "stock": 28},
    {"id": 9, "name": "Yoga Mat", "price": 2499, "category": "Fitness", "stock": 35},
    {"id": 10, "name": "Coffee Grinder", "price": 5499, "category": "Kitchen", "stock": 15},
]
for product in PRODUCTS:
    product["currency"] = APP_CURRENCY

orders = []
orders_lock = threading.Lock()
app_health_lock = threading.Lock()
app_healthy = True
cpu_stress_lock = threading.Lock()
cpu_stress_running = False
memory_allocation = None

UI_TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ShopEase Operations Console</title>
  <style>
    :root { --bg:#08111f; --panel:#101d30; --line:#223652; --text:#edf5ff; --muted:#91a6c2; --blue:#58a6ff; --green:#35d07f; --red:#ff6577; --amber:#ffbd5a; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--text); background:radial-gradient(circle at top left,#142d50 0,#08111f 40%); font-family:Inter,Segoe UI,sans-serif; min-height:100vh; }
    button, input { font:inherit; }
    .shell { max-width:1280px; margin:auto; padding:28px; }
    header { display:flex; justify-content:space-between; gap:20px; align-items:center; margin-bottom:24px; }
    h1,h2,p { margin:0; }
    h1 { font-size:30px; letter-spacing:-1px; }
    h2 { font-size:17px; }
    .eyebrow { color:var(--blue); text-transform:uppercase; font-size:11px; font-weight:800; letter-spacing:2px; margin-bottom:7px; }
    .muted { color:var(--muted); font-size:13px; }
    .status { display:flex; align-items:center; gap:9px; padding:10px 15px; border:1px solid var(--line); border-radius:99px; background:#0b1728; font-weight:700; }
    .dot { width:9px; height:9px; border-radius:50%; background:var(--green); box-shadow:0 0 14px var(--green); }
    .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:15px; margin-bottom:20px; }
    .card { background:linear-gradient(145deg,rgba(16,29,48,.96),rgba(10,23,40,.96)); border:1px solid var(--line); border-radius:14px; padding:18px; box-shadow:0 12px 35px rgba(0,0,0,.2); }
    .metric strong { display:block; font-size:28px; margin-top:7px; }
    .layout { display:grid; grid-template-columns:1.6fr 1fr; gap:20px; }
    .section-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; }
    .products { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; max-height:630px; overflow:auto; padding-right:4px; }
    .product { border:1px solid var(--line); border-radius:12px; padding:15px; background:#0b1728; }
    .product-top { display:flex; justify-content:space-between; gap:10px; }
    .tag { color:var(--blue); background:#102c4b; padding:4px 8px; border-radius:99px; font-size:10px; font-weight:800; text-transform:uppercase; }
    .price { color:var(--green); font-size:20px; font-weight:800; margin:13px 0 10px; }
    .order-row { display:flex; gap:8px; }
    input { width:60px; border:1px solid var(--line); border-radius:8px; background:#08111f; color:var(--text); padding:8px; }
    button,.link { cursor:pointer; border:0; border-radius:8px; background:var(--blue); color:#06111f; padding:8px 11px; font-weight:800; text-decoration:none; font-size:12px; }
    button:hover,.link:hover { filter:brightness(1.12); }
    .danger { background:var(--red); } .warn { background:var(--amber); } .success { background:var(--green); }
    .actions { display:grid; grid-template-columns:repeat(2,1fr); gap:9px; margin:14px 0 18px; }
    .actions button { min-height:42px; }
    .links { display:flex; flex-wrap:wrap; gap:8px; }
    .links .link { background:#172a44; color:var(--text); }
    .orders { margin-top:20px; }
    .order { display:grid; grid-template-columns:1fr auto auto; gap:10px; align-items:center; padding:11px 0; border-bottom:1px solid var(--line); }
    .remove { background:transparent; color:var(--red); border:1px solid var(--red); }
    .order:last-child { border:0; }
    .toast { position:fixed; right:25px; bottom:25px; max-width:360px; padding:13px 16px; border-radius:10px; background:#142a45; border:1px solid var(--blue); display:none; box-shadow:0 10px 30px #0008; }
    @media(max-width:900px){ .grid{grid-template-columns:repeat(2,1fr)} .layout{grid-template-columns:1fr} }
    @media(max-width:560px){ .shell{padding:16px} header{align-items:flex-start;flex-direction:column}.grid,.products{grid-template-columns:1fr} }
  </style>
</head>
<body>
<main class="shell">
  <header>
    <div><div class="eyebrow">Production Operations Lab</div><h1>ShopEase Control Center</h1><p class="muted">API v{{ version }} · {{ environment }} environment</p></div>
    <div class="status"><span class="dot" id="healthDot"></span><span id="healthLabel">Checking health...</span></div>
  </header>
  <section class="grid">
    <div class="card metric"><span class="muted">Uptime</span><strong id="uptime">--</strong></div>
    <div class="card metric"><span class="muted">Products</span><strong id="productCount">--</strong></div>
    <div class="card metric"><span class="muted">Orders placed</span><strong id="orderCount">--</strong></div>
    <div class="card metric"><span class="muted">Available stock</span><strong id="stockCount">--</strong></div>
  </section>
  <section class="layout">
    <div class="card">
      <div class="section-head"><div><h2>Product Catalog</h2><p class="muted">Place orders against the in-memory API</p></div><button onclick="loadAll()">Refresh</button></div>
      <div class="products" id="products"></div>
    </div>
    <aside>
      <div class="card">
        <h2>Failure Simulations</h2><p class="muted">Trigger observable incidents and recovery events</p>
        <div class="actions">
          <button class="warn" onclick="simulate('cpu')">High CPU</button>
          <button class="warn" onclick="simulate('memory')">Memory +100MB</button>
          <button class="warn" onclick="simulate('disk')">Write 50MB</button>
          <button class="danger" onclick="simulate('crash')">Crash Health</button>
          <button class="success" onclick="simulate('recover')">Recover</button>
        </div>
        <h2>API Observability</h2>
        <div class="links">
          <a class="link" href="/health" target="_blank">Health JSON</a>
          <a class="link" href="/metrics" target="_blank">Prometheus Metrics</a>
          <a class="link" href="/api/info" target="_blank">API Info</a>
          <a class="link" href="/orders" target="_blank">Orders JSON</a>
        </div>
      </div>
      <div class="card orders">
        <div class="section-head"><div><h2>Recent Orders</h2><p class="muted">Newest confirmed orders</p></div></div>
        <div id="orders"></div>
      </div>
    </aside>
  </section>
</main>
<div class="toast" id="toast"></div>
<script>
  const money = value => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(value);
  const toast = (message, bad=false) => { const el=document.getElementById('toast'); el.textContent=message; el.style.display='block'; el.style.borderColor=bad?'var(--red)':'var(--blue)'; setTimeout(()=>el.style.display='none',3500); };
  async function api(path, options={}) { const r=await fetch(path,options); const data=await r.json(); if(!r.ok) throw new Error(data.error || `Request failed: ${r.status}`); return data; }
  async function loadHealth() {
    try { const h=await api('/health'); document.getElementById('healthLabel').textContent='Healthy'; document.getElementById('healthDot').style.background='var(--green)'; document.getElementById('uptime').textContent=Math.floor(h.uptime_seconds)+'s'; }
    catch(e) { document.getElementById('healthLabel').textContent='Unhealthy'; document.getElementById('healthDot').style.background='var(--red)'; }
  }
  async function loadProducts() {
    const data=await api('/products'); document.getElementById('productCount').textContent=data.count; document.getElementById('stockCount').textContent=data.products.reduce((a,p)=>a+p.stock,0);
    document.getElementById('products').innerHTML=data.products.map(p=>`<article class="product"><div class="product-top"><strong>${p.name}</strong><span class="tag">${p.category}</span></div><div class="price">${money(p.price)}</div><div class="order-row"><input id="qty-${p.id}" type="number" min="1" max="${p.stock}" value="1"><button onclick="order(${p.id})">Order</button><span class="muted">${p.stock} in stock</span></div></article>`).join('');
  }
  async function loadOrders() {
    const data=await api('/orders'); document.getElementById('orderCount').textContent=data.count;
    document.getElementById('orders').innerHTML=data.orders.length ? data.orders.slice().reverse().slice(0,6).map(o=>`<div class="order"><div><strong>${o.product_name}</strong><div class="muted">Qty ${o.quantity} · ${o.id.slice(0,8)}</div></div><strong>${money(o.total_price)}</strong><button class="remove" onclick="removeOrder('${o.id}')">Remove</button></div>`).join('') : '<p class="muted">No orders yet. Place one from the catalog.</p>';
  }
  async function order(productId) {
    try { const quantity=Number(document.getElementById(`qty-${productId}`).value); const data=await api('/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_id:productId,quantity})}); toast(`Order confirmed: ${data.order.product_name}`); await loadAll(); } catch(e){ toast(e.message,true); }
  }
  async function removeOrder(orderId) {
    if(!confirm('Remove this order and restore its product stock?')) return;
    try { const data=await api(`/orders/${orderId}`,{method:'DELETE'}); toast(data.message); await loadAll(); } catch(e){ toast(e.message,true); }
  }
  async function simulate(type) {
    if(type==='crash' && !confirm('Mark the service unhealthy and make /health return 503?')) return;
    try { const data=await api(`/simulate/${type}`); toast(data.message || `${type} simulation triggered`); setTimeout(loadHealth,300); } catch(e){ toast(e.message,true); setTimeout(loadHealth,300); }
  }
  async function loadAll(){ try{ await Promise.all([loadHealth(),loadProducts(),loadOrders()]); }catch(e){ toast(e.message,true); } }
  loadAll(); setInterval(loadHealth,5000);
</script>
</body>
</html>
"""


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def error_response(message, status_code, details=None):
    payload = {
        "error": message,
        "status": status_code,
        "timestamp": utc_timestamp(),
    }
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


def find_product(product_id):
    return next((product for product in PRODUCTS if product["id"] == product_id), None)


def set_app_health(healthy):
    global app_healthy
    with app_health_lock:
        app_healthy = healthy
        APP_HEALTH.set(1 if healthy else 0)


def is_app_healthy():
    with app_health_lock:
        return app_healthy


def route_label():
    return request.url_rule.rule if request.url_rule else "unmatched"


@app.before_request
def before_request():
    g.request_started_at = time.monotonic()
    ACTIVE_REQUESTS.inc()


@app.after_request
def after_request(response):
    endpoint = route_label()
    elapsed = time.monotonic() - g.get("request_started_at", time.monotonic())
    REQUESTS_TOTAL.labels(request.method, endpoint, str(response.status_code)).inc()
    REQUEST_LATENCY.labels(endpoint).observe(elapsed)
    ACTIVE_REQUESTS.dec()
    logger.info(
        "request method=%s endpoint=%s status=%s latency_seconds=%.4f",
        request.method,
        endpoint,
        response.status_code,
        elapsed,
    )
    return response


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    return error_response(exc.description, exc.code)


@app.errorhandler(Exception)
def handle_unexpected_exception(exc):
    logger.exception("Unhandled application error")
    return error_response("Internal server error", 500)


@app.get("/")
def welcome():
    return render_template_string(UI_TEMPLATE, version=APP_VERSION, environment=APP_ENV)


@app.get("/api/info")
def api_info():
    return jsonify(
        {
            "name": APP_NAME,
            "message": "Welcome to the ShopEase e-commerce REST API",
            "version": APP_VERSION,
            "environment": APP_ENV,
            "currency": APP_CURRENCY,
            "documentation": {
                "health": "/health",
                "metrics": "/metrics",
                "products": "/products",
                "orders": "/orders",
            },
        }
    )


@app.get("/health")
def health():
    healthy = is_app_healthy()
    status_code = 200 if healthy else 503
    return (
        jsonify(
            {
                "status": "healthy" if healthy else "unhealthy",
                "uptime_seconds": round(time.monotonic() - START_TIME, 2),
                "timestamp": utc_timestamp(),
                "version": APP_VERSION,
                "environment": APP_ENV,
            }
        ),
        status_code,
    )


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.get("/products")
def list_products():
    return jsonify({"count": len(PRODUCTS), "products": PRODUCTS})


@app.get("/products/<int:product_id>")
def get_product(product_id):
    product = find_product(product_id)
    if product is None:
        return error_response("Product not found", 404)

    PRODUCTS_VIEWED_TOTAL.labels(str(product_id)).inc()
    return jsonify(product)


@app.post("/orders")
def create_order():
    if not request.is_json:
        return error_response("Content-Type must be application/json", 415)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("Request body must be a JSON object", 400)

    product_id = payload.get("product_id")
    quantity = payload.get("quantity")
    if isinstance(product_id, bool) or not isinstance(product_id, int):
        return error_response("product_id must be an integer", 400)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return error_response("quantity must be a positive integer", 400)

    with orders_lock:
        product = find_product(product_id)
        if product is None:
            return error_response("Product not found", 404)
        if quantity > product["stock"]:
            return error_response(
                "Insufficient stock",
                409,
                {"available": product["stock"], "requested": quantity},
            )

        product["stock"] -= quantity
        order = {
            "id": str(uuid.uuid4()),
            "product_id": product["id"],
            "product_name": product["name"],
            "quantity": quantity,
            "unit_price": product["price"],
            "total_price": round(product["price"] * quantity, 2),
            "currency": APP_CURRENCY,
            "status": "confirmed",
            "created_at": utc_timestamp(),
        }
        orders.append(order)

    ORDERS_TOTAL.inc()
    logger.info(
        "order_created order_id=%s product_id=%s quantity=%s",
        order["id"],
        product_id,
        quantity,
    )
    return jsonify({"message": "Order created successfully", "order": order}), 201


@app.get("/orders")
def list_orders():
    with orders_lock:
        order_snapshot = list(orders)
    return jsonify({"count": len(order_snapshot), "orders": order_snapshot})


@app.get("/orders/<order_id>")
def get_order(order_id):
    with orders_lock:
        order = next((item for item in orders if item["id"] == order_id), None)
    if order is None:
        return error_response("Order not found", 404)
    return jsonify(order)


@app.delete("/orders/<order_id>")
def delete_order(order_id):
    with orders_lock:
        order_index = next(
            (index for index, item in enumerate(orders) if item["id"] == order_id),
            None,
        )
        if order_index is None:
            return error_response("Order not found", 404)

        order = orders.pop(order_index)
        product = find_product(order["product_id"])
        if product is not None:
            product["stock"] += order["quantity"]

    logger.info(
        "order_removed order_id=%s product_id=%s quantity=%s",
        order["id"],
        order["product_id"],
        order["quantity"],
    )
    return jsonify({"message": "Order removed and stock restored", "order": order})


def run_cpu_stress():
    global cpu_stress_running
    logger.warning("CPU stress simulation started")
    deadline = time.monotonic() + 30
    value = 1
    while time.monotonic() < deadline:
        value = (value * 3 + 7) % 1_000_003
    with cpu_stress_lock:
        cpu_stress_running = False
    logger.warning("CPU stress simulation completed final_value=%s", value)


@app.get("/simulate/cpu")
def simulate_cpu():
    global cpu_stress_running
    with cpu_stress_lock:
        if cpu_stress_running:
            return error_response("CPU stress simulation is already running", 409)
        cpu_stress_running = True
        threading.Thread(target=run_cpu_stress, daemon=True).start()
    return jsonify({"message": "CPU stress simulation started", "duration_seconds": 30}), 202


@app.get("/simulate/memory")
def simulate_memory():
    global memory_allocation
    memory_allocation = bytearray(100 * 1024 * 1024)
    logger.warning("Memory simulation allocated approximately 100 MiB")
    return jsonify({"message": "Memory allocation completed", "allocated_megabytes": 100})


@app.get("/simulate/crash")
def simulate_crash():
    set_app_health(False)
    logger.error("Crash simulation triggered; application marked unhealthy")
    return error_response("Simulated application failure", 500)


@app.get("/simulate/recover")
def simulate_recover():
    set_app_health(True)
    logger.warning("Recovery simulation triggered; application marked healthy")
    return jsonify({"message": "Application recovered", "health": "healthy"})


@app.get("/simulate/disk")
def simulate_disk():
    file_path = "/tmp/shopease-dummy.bin"
    chunk = b"0" * (1024 * 1024)
    try:
        with open(file_path, "wb") as dummy_file:
            for _ in range(50):
                dummy_file.write(chunk)
    except OSError as exc:
        logger.exception("Disk simulation failed")
        return error_response("Disk write simulation failed", 507, str(exc))

    logger.warning("Disk simulation wrote 50 MiB to %s", file_path)
    return jsonify(
        {
            "message": "Disk write simulation completed",
            "file": file_path,
            "written_megabytes": 50,
        }
    )


if __name__ == "__main__":
    logger.info(
        "Starting %s version=%s environment=%s port=%s",
        APP_NAME,
        APP_VERSION,
        APP_ENV,
        PORT,
    )
    app.run(host="0.0.0.0", port=PORT, threaded=True)
