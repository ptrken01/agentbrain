"""
AgentBrain Auth Service — Subscription & API Key Management
"""
import os
import json
import hashlib
import secrets
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
import stripe

# Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID", "price_1U5OUhDxZTiv22XcmA4OF2ds")
STRIPE_TEAM_PRICE_ID = os.environ.get("STRIPE_TEAM_PRICE_ID", "price_1U5OUjDxZTiv22Xck71tvMPu")

stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI(title="AgentBrain Auth Service")

def get_db():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            api_key TEXT UNIQUE,
            tier TEXT DEFAULT 'free',
            stripe_customer_id TEXT,
            subscription_id TEXT,
            subscription_status TEXT DEFAULT 'inactive',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

# Try to init db on startup
try:
    init_db()
except Exception as e:
    print(f"DB init warning: {e}")

def get_tier_features(tier: str) -> list:
    if tier == "free":
        return ["basic_search", "remember", "recall"]
    elif tier == "pro":
        return ["basic_search", "advanced_search", "remember", "recall", "context_packs", "agent_discovery", "knowledge_graph"]
    elif tier == "team":
        return ["basic_search", "advanced_search", "remember", "recall", "context_packs", "agent_discovery", "knowledge_graph", "team_brain", "marketplace", "audit_trail"]
    return []

def get_tier_limit(user_tier: str, limit: str) -> int:
    limits = {
        "free": {"max_memories": 1000, "max_api_calls_per_day": 100},
        "pro": {"max_memories": 50000, "max_api_calls_per_day": 10000},
        "team": {"max_memories": 999999999, "max_api_calls_per_day": 1000000}
    }
    return limits.get(user_tier, limits["free"]).get(limit, 0)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_api_key() -> str:
    return f"ab_{secrets.token_urlsafe(32)}"

def get_user(api_key: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE api_key = %s", (api_key,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

@app.get("/")
async def root():
    return {"status": "ok", "service": "AgentBrain Auth"}

@app.post("/auth/register")
async def register(request: Request):
    data = await request.json()
    email = data.get("email", "")
    password = data.get("password", "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    api_key = generate_api_key()
    cur.execute(
        "INSERT INTO users (email, password_hash, api_key) VALUES (%s, %s, %s)",
        (email, hash_password(password), api_key)
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"api_key": api_key, "tier": "free"}

@app.post("/auth/login")
async def login(request: Request):
    data = await request.json()
    email = data.get("email", "")
    password = data.get("password", "")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s AND password_hash = %s",
                (email, hash_password(password)))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"api_key": user["api_key"], "tier": user["tier"]}

@app.get("/auth/limits")
async def limits(x_api_key: str = Header(...)):
    user = get_user(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    tier = user["tier"]
    return {
        "tier": tier,
        "max_memories": get_tier_limit(tier, "max_memories"),
        "max_api_calls_per_day": get_tier_limit(tier, "max_api_calls_per_day"),
        "features": get_tier_features(tier)
    }

@app.post("/auth/verify")
async def verify(api_key: str = Header(...)):
    user = get_user(api_key)
    if not user:
        return {"valid": False, "tier": "free", "features": get_tier_features("free")}
    return {
        "valid": True,
        "tier": user["tier"],
        "features": get_tier_features(user["tier"])
    }

@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("details", {}).get("email")
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        line_items = stripe.checkout.Session.list_line_items(session["id"])
        tier = "free"
        for item in line_items["data"]:
            if item["price"]["id"] == STRIPE_PRO_PRICE_ID:
                tier = "pro"
            elif item["price"]["id"] == STRIPE_TEAM_PRICE_ID:
                tier = "team"
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (customer_email,))
        user = cur.fetchone()
        if user:
            cur.execute("UPDATE users SET tier=%s, stripe_customer_id=%s, subscription_id=%s, subscription_status=%s WHERE id=%s",
                        (tier, customer_id, subscription_id, "active", user["id"]))
        else:
            api_key = generate_api_key()
            cur.execute("INSERT INTO users (email, api_key, tier, stripe_customer_id, subscription_id, subscription_status) VALUES (%s,%s,%s,%s,%s,%s)",
                        (customer_email, api_key, tier, customer_id, subscription_id, "active"))
        conn.commit()
        cur.close()
        conn.close()
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET tier='free', subscription_status='cancelled' WHERE stripe_customer_id=%s",
                    (subscription["customer"],))
        conn.commit()
        cur.close()
        conn.close()
    return {"status": "ok"}
