"""
AgentBrain Auth Service — Subscription & API Key Management
Uses PostgreSQL for persistent storage
"""
import os
import json
import hashlib
import secrets
import time
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import stripe
import asyncpg

# Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/agentbrain")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI(title="AgentBrain Auth Service")

@app.get("/")
async def root():
    return {"status": "ok", "service": "AgentBrain Auth", "version": "1.0", "database": "postgresql"}

# Database setup
db_pool: asyncpg.Pool = None

@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    async with db_pool.acquire() as conn:
        await conn.execute("""
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_limits (
                tier TEXT PRIMARY KEY,
                max_memories INTEGER,
                max_api_calls_per_day INTEGER,
                features TEXT
            );
        """)
        # Insert default tiers
        await conn.execute("""
            INSERT INTO memory_limits (tier, max_memories, max_api_calls_per_day, features) 
            VALUES ('free', 1000, 100, '["basic_search"]')
            ON CONFLICT (tier) DO NOTHING;
        """)
        await conn.execute("""
            INSERT INTO memory_limits (tier, max_memories, max_api_calls_per_day, features) 
            VALUES ('pro', 50000, 10000, '["basic_search", "advanced_search", "context_packs", "agent_discovery"]')
            ON CONFLICT (tier) DO NOTHING;
        """)
        await conn.execute("""
            INSERT INTO memory_limits (tier, max_memories, max_api_calls_per_day, features) 
            VALUES ('team', 999999999, 1000000, '["basic_search", "advanced_search", "context_packs", "agent_discovery", "team_brain", "marketplace", "audit_trail"]')
            ON CONFLICT (tier) DO NOTHING;
        """)

async def get_db():
    async with db_pool.acquire() as conn:
        yield conn

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
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE api_key = $1", x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return dict(user)

def get_tier_features(tier: str) -> list:
    """Get features for a tier"""
    if tier == "free":
        return ["basic_search", "remember", "recall"]
    elif tier == "pro":
        return ["basic_search", "advanced_search", "remember", "recall", "context_packs", "agent_discovery", "knowledge_graph"]
    elif tier == "team":
        return ["basic_search", "advanced_search", "remember", "recall", "context_packs", "agent_discovery", "knowledge_graph", "team_brain", "marketplace", "audit_trail"]
    return []

def get_tier_limit(user_tier: str, limit: str) -> int:
    """Get limit for a tier"""
    limits = {
        "free": {"max_memories": 1000, "max_api_calls_per_day": 100},
        "pro": {"max_memories": 50000, "max_api_calls_per_day": 10000},
        "team": {"max_memories": 999999999, "max_api_calls_per_day": 1000000}
    }
    return limits.get(user_tier, limits["free"]).get(limit, 0)

# Routes
@app.post("/auth/register")
async def register(req: RegisterRequest):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", req.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        api_key = generate_api_key()
        password_hash = hash_password(req.password)

        await conn.execute(
            "INSERT INTO users (email, password_hash, api_key) VALUES ($1, $2, $3)",
            req.email, password_hash, api_key
        )

    return {"api_key": api_key, "tier": "free", "message": "Registration successful. Upgrade to Pro for more features."}

@app.post("/auth/login")
async def login(req: LoginRequest):
    password_hash = hash_password(req.password)
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE email = $1 AND password_hash = $2",
            req.email, password_hash
        )

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

@app.post("/auth/verify")
async def verify(api_key: str = Header(...)):
    """Verify an API key and return tier info (used by MCP server)"""
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE api_key = $1", api_key)

    if not user:
        return {"valid": False, "tier": "free", "features": get_tier_features("free")}

    return {
        "valid": True,
        "tier": user["tier"],
        "features": get_tier_features(user["tier"]),
        "subscription_status": user["subscription_status"]
    }

# Stripe webhook
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
        await handle_successful_payment(session)
    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        await handle_subscription_update(subscription)
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        await handle_subscription_cancelled(subscription)

    return {"status": "ok"}

async def handle_successful_payment(session: dict):
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    customer_email = session.get("details", {}).get("email")

    # Determine tier from price
    line_items = stripe.checkout.Session.list_line_items(session["id"])
    tier = "free"
    for item in line_items["data"]:
        price_id = item["price"]["id"]
        if price_id == os.environ.get("STRIPE_PRO_PRICE_ID", ""):
            tier = "pro"
        elif price_id == os.environ.get("STRIPE_TEAM_PRICE_ID", ""):
            tier = "team"

    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE email = $1", customer_email)
        if user:
            await conn.execute(
                "UPDATE users SET tier = $1, stripe_customer_id = $2, subscription_id = $3, subscription_status = $4, updated_at = NOW() WHERE id = $5",
                tier, customer_id, subscription_id, "active", user["id"]
            )
        else:
            api_key = generate_api_key()
            await conn.execute(
                "INSERT INTO users (email, api_key, tier, stripe_customer_id, subscription_id, subscription_status) VALUES ($1, $2, $3, $4, $5, $6)",
                customer_email, api_key, tier, customer_id, subscription_id, "active"
            )

async def handle_subscription_update(subscription: dict):
    customer_id = subscription["customer"]
    status = subscription["status"]

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET subscription_status = $1, updated_at = NOW() WHERE stripe_customer_id = $2",
            status, customer_id
        )

async def handle_subscription_cancelled(subscription: dict):
    customer_id = subscription["customer"]

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET tier = 'free', subscription_status = 'cancelled', subscription_id = NULL, updated_at = NOW() WHERE stripe_customer_id = $1",
            customer_id
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
