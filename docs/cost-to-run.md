# Cost to run

Estimates in US dollars, to be confirmed after the deploy. Prices: AWS on-demand (us-east-1) and the Claude API pricing page, October 2026.

## Infrastructure

| Item | Monthly |
|---|---|
| EC2 t4g.small (2 vCPU, 2 GB): Nginx, API and PostgreSQL on one machine | ~ US$ 12.30 |
| EBS gp3, 20 GB | ~ US$ 1.60 |
| Domain and HTTPS (Let's Encrypt) | ~ US$ 1 (domain, yearly price / 12) |
| **Total** | **~ US$ 15** |

One small machine is enough for a portfolio: each demo copy is about 600 rows, the cap of 500 live copies is ~300k rows, far below what PostgreSQL handles on 2 GB.

## Per household

| Item | Cost |
|---|---|
| Receipt reading (Claude Haiku 5.5) | ~ US$ 0.0007 per receipt |
| A household that shops 10 times a month | < US$ 0.01 a month in AI |
| Public demo visitor | US$ 0 in AI (sample receipt) |

## Where the cost grows

1. **More households:** the database first. Past a few thousand active households, PostgreSQL moves to RDS (~ US$ 15–30 more) and the API scales on its own.
2. **Receipt reading open to everyone:** linear with the number of receipts; a per-household limit keeps it predictable (see [the decision](decisions/receipt-reading.md)).
3. **Polling of the shared list (every 3 s while shopping):** cheap requests, only while someone is in a store. WebSockets would replace it if it ever mattered.
