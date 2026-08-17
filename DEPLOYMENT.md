# AgentBrain Deployment Guide

## Architecture

```
User → brain.autoincomesys.com (static site)
     → Subscribe via Stripe → Payment confirmed
     → Stripe webhook → auth_service.py
     → API key generated, tier granted
     → User uses API key with MCP server
     → MCP server verifies tier on every request
```

## Services

### 1. Static Site (GitHub Pages)
- **Repo**: `ptrken01/agentbrain`
- **URL**: `brain.autoincomesys.com`
- **Content**: Landing page, docs, blog, setup guide

### 2. Auth Service (Needs hosting)
- **File**: `auth_service.py`
- **Purpose**: User registration, API keys, Stripe webhooks
- **Database**: SQLite (upgrade to PostgreSQL for production)
- **URL**: `https://auth.agentbrain.io`

### 3. MCP Server (Needs hosting)
- **File**: `server.py`
- **Purpose**: Gated MCP tools (remember, recall, knowledge graph, marketplace)
- **URL**: `https://mcp.agentbrain.io`

## Subscription Tiers & Feature Gating

| Feature | Free | Pro ($20/mo) | Team ($99/mo) |
|---------|------|--------------|---------------|
| Remember & Recall | ✅ | ✅ | ✅ |
| Basic Search | ✅ | ✅ | ✅ |
| Memories/month | 1,000 | 50,000 | Unlimited |
| Advanced Search | ❌ | ✅ | ✅ |
| Knowledge Graph | ❌ | ✅ | ✅ |
| Agent Discovery | ❌ | ✅ | ✅ |
| Context Packs | ❌ | ✅ | ✅ |
| Agent Marketplace | ❌ | ❌ | ✅ |
| Register Agents | ❌ | ❌ | ✅ |
| Team Brain | ❌ | ❌ | ✅ |
| Audit Trail | ❌ | ❌ | ✅ |

### How Gating Works

1. User subscribes via Stripe Checkout
2. Stripe sends `checkout.session.completed` webhook
3. Auth service creates user record with tier + generates API key
4. Auth service emails API key to user
5. User adds API key to their MCP client config
6. On every MCP request, server calls auth service to verify tier
7. If tier doesn't have feature → API returns "Upgrade required"
8. If subscription expires/cancels → Stripe webhook downgrades to free

### Anti-Scam Protection

- **Technical enforcement**: Features are gated at the API level, not just UI
- **No pay-to-promise**: Users get working API keys immediately after payment
- **Transparent limits**: `/auth/limits` endpoint shows exactly what you have
- **Cancel anytime**: Subscription managed by Stripe, automatic downgrade
- **No lock-in**: Export your data anytime

## Deployment Steps

### 1. Host Auth Service
Deploy `auth_service.py` to a cloud provider:
- **Free option**: Railway, Render, or Fly.io free tiers
- **Environment variables needed**:
  - `STRIPE_SECRET_KEY`: Your Stripe secret key
  - `STRIPE_WEBHOOK_SECRET`: From Stripe webhook config
  - `DATABASE_URL`: PostgreSQL connection string

### 2. Configure Stripe Webhook
In Stripe Dashboard → Developers → Webhooks:
- **Endpoint URL**: `https://auth.agentbrain.io/webhooks/stripe`
- **Events to listen for**:
  - `checkout.session.completed`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
- **Signing secret**: Set as `STRIPE_WEBHOOK_SECRET`

### 3. Host MCP Server
Deploy `server.py` to the same or different host:
- **Environment variables**:
  - `AUTH_SERVICE_URL`: URL of your auth service
- **URL**: `https://mcp.agentbrain.io`

### 4. Update Stripe Payment Links
Update `success_url` to point to your setup page:
```
https://brain.autoincomesys.com/setup.html?session_id={CHECKOUT_SESSION_ID}
```

### 5. Test the Flow
1. Subscribe with test card `4242 4242 4242 4242`
2. Verify webhook fires
3. Check API key is generated
4. Test MCP tools with the API key
5. Verify gating works (try premium feature with free key)

## Production Checklist

- [ ] PostgreSQL database (not SQLite)
- [ ] HTTPS on all endpoints
- [ ] Email sending (SendGrid/Resend for API key delivery)
- [ ] Rate limiting on auth endpoints
- [ ] Monitoring & alerting
- [ ] Backup strategy
- [ ] Terms of Service + Privacy Policy
- [ ] Stripe account fully activated (not in test mode)
