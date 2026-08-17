import sqlite3
import hashlib
import secrets
import json
import time
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import stripe
import uvicorn

# Configuration
DATABASE = "agentbrain.db"
STRIPE_WEBHOOK_SECRET = "whsec_your_webhook_secret"  # Set from environment
STRIPE_SECRET_KEY = "sk_live_your_key"  # Set from environment

stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI(title="AgentBrain Auth Service")

# Database setup
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            api_key TEXT UNIQUE,
            tier TEXT DEFAULT 'free',
            stripe_customer_id TEXT,
            subscription_id TEXT,
            subscription_status TEXT DEFAULT 'inactive',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS memory_limits (
            tier TEXT PRIMARY KEY,
            max_memories INTEGER,
            max_api_calls_per_day INTEGER,
            features TEXT
        );

        INSERT OR IGNORE INTO memory_limits VALUES 
            ('free', 1000, 100, '["basic_search"]'),
            ('pro', 50000, 10000, '["basic_search", "advanced_search", "context_packs", "agent_discovery"]'),
            ('team', 999999999, 1000000, '["basic_search", "advanced_search", "context_packs", "agent_discovery", "team_brain", "marketplace", "audit_trail"]');
    """)
    conn.commit()
    conn.close()

init_db()

# Models
class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_api_key() -> str:
    return f"ab_{secrets.token_urlsafe(32)}"

async def get_current_user(x_api_key: str = Header(...)):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE api_key = ?", (x_api_key,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return dict(user)

def get_tier_features(tier: str) -> list:
    conn = get_db()
    row = conn.execute("SELECT features FROM memory_limits WHERE tier = ?", (tier,)).fetchone()
    conn.close()
    if not row:
        return []
    return json.loads(row["features"])

def get_tier_limit(user_tier: str, limit: str) -> int:
    conn = get_db()
    row = conn.execute(f"SELECT {limit} FROM memory_limits WHERE tier = ?", (user_tier,)).fetchone()
    conn.close()
    return row[limit] if row else 0

# Routes
@app.post("/auth/register")
async def register(req: RegisterRequest):
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (req.email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")

    api_key = generate_api_key()
    password_hash = hash_password(req.password)

    conn.execute(
        "INSERT INTO users (email, password_hash, api_key) VALUES (?, ?, ?)",
        (req.email, password_hash, api_key)
    )
    conn.commit()
    conn.close()

    return {"api_key": api_key, "tier": "free", "message": "Registration successful. Upgrade to Pro for more features."}

@app.post("/auth/login")
async def login(req: LoginRequest):
    conn = get_db()
    password_hash = hash_password(req.password)
    user = conn.execute(
        "SELECT * FROM users WHERE email = ? AND password_hash = ?",
        (req.email, password_hash)
    ).fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {"api_key": user["api_key"], "tier": user["tier"]}

@app.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {
        "email": user["email"],
        "tier": user["tier"],
        "subscription_status": user["subscription_status"],
        "features": get_tier_features(user["tier"])
    }

@app.get("/auth/limits")
async def limits(user: dict = Depends(get_current_user)):
    tier = user["tier"]
    return {
        "tier": tier,
        "max_memories": get_tier_limit(tier, "max_memories"),
        "max_api_calls_per_day": get_tier_limit(tier, "max_api_calls_per_day"),
        "features": get_tier_features(tier)
    }

# Stripe webhooks
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        handle_successful_payment(session)
    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        handle_subscription_update(subscription)
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        handle_subscription_cancelled(subscription)

    return {"status": "ok"}

def handle_successful_payment(session: dict):
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    customer_email = session.get("details", {}).get("email")

    # Determine tier from price
    line_items = stripe.checkout.Session.list_line_items(session["id"])
    tier = "free"
    for item in line_items["data"]:
        price_id = item["price"]["id"]
        if "price_1U5OUhDxZTiv22XcmA4OF2ds" in price_id:
            tier = "pro"
        elif "price_1U5OUjDxZTiv22Xck71tvMPu" in price_id:
            tier = "team"

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (customer_email,)).fetchone()
    if user:
        conn.execute(
            "UPDATE users SET tier = ?, stripe_customer_id = ?, subscription_id = ?, subscription_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (tier, customer_id, subscription_id, "active", user["id"])
        )
    else:
        api_key = generate_api_key()
        conn.execute(
            "INSERT INTO users (email, api_key, tier, stripe_customer_id, subscription_id, subscription_status) VALUES (?, ?, ?, ?, ?, ?)",
            (customer_email, api_key, tier, customer_id, subscription_id, "active")
        )
    conn.commit()
    conn.close()

def handle_subscription_update(subscription: dict):
    customer_id = subscription["customer"]
    status = subscription["status"]

    conn = get_db()
    conn.execute(
        "UPDATE users SET subscription_status = ?, updated_at = CURRENT_TIMESTAMP WHERE stripe_customer_id = ?",
        (status, customer_id)
    )
    conn.commit()
    conn.close()

def handle_subscription_cancelled(subscription: dict):
    customer_id = subscription["customer"]

    conn = get_db()
    conn.execute(
        "UPDATE users SET tier = 'free', subscription_status = 'cancelled', subscription_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE stripe_customer_id = ?",
        (customer_id,)
    )
    conn.commit()
    conn.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
