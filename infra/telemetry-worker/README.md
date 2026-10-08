# Locdex telemetry ingress (Cloudflare Workers)

Minimal open-source launch backend for the **BASIC** Locdex telemetry schema (v1). It uses Cloudflare's Workers runtime, rate limiting, Workers Analytics Engine, and R2. It does **not** need PostHog, Aptabase, Kafka, or ClickHouse at launch.

The public API is `POST /v1/events`; `GET /health` is a health check. There is no public read/export or admin API. **The Worker is not deployed merely by merging this code.**

## 1. Deploy (Cloudflare account required)

From this directory, with Node 20+:

```bash
npm install
npm test
npm run check
npx wrangler login
npx wrangler r2 bucket create locdex-telemetry-events
npx wrangler deploy
```

The first successful ingestion auto-creates the `locdex_routing` Analytics Engine dataset. Wrangler returns a live `https://<worker>.<subdomain>.workers.dev` URL. Do not invent this URL or publish one before the Worker is actually deployed.

The production config is `wrangler.jsonc`. The R2 bucket is private: no R2 public domain binding, token, or API key is shipped to Locdex clients. Cloudflare bindings provide storage access.

## 2. Point the Locdex client at the deployed Worker

From the Locdex application checkout:

```bash
locdex telemetry endpoint https://YOUR-DEPLOYED-WORKER.workers.dev/v1/events
locdex telemetry status
locdex telemetry preview
locdex telemetry flush
```

BASIC is on by default in this release, with a first-use disclosure and immediate opt-out:

```bash
locdex telemetry disable
locdex telemetry clear
```

`disable` also clears unsent queued metrics. `LOCDEX_TELEMETRY_MODE=off` suppresses telemetry regardless of file configuration.

Use a custom domain like `telemetry.your-domain.tld` only after configuring its Worker route in Cloudflare. There is no automatic default URL compiled into Locdex until that real domain is deployed and verified.

## 3. Launch behavior

The client queues one sanitized routing outcome at each agent attempt, then attempts a short bounded flush after the task. Failure never breaks coding work; the queue retries at the next run or via `locdex telemetry flush`. Endpoint URL must be HTTPS.

The server rejects extra fields, unexpected types, free-form strings, oversized payloads, >25 events/batch, unsupported versions, and unsupported request methods. It never persists request IPs, HTTP headers, prompts, code, repository paths, user IDs, or installation IDs. Random R2 object keys do not track installations.

R2 stores canonical sanitized batches under `v1/YYYY-MM-DD/<random>.json`, while Analytics Engine stores a short ordered projection. `blob1` = event, `blob2` = task class, `blob6` = model, `blob7` = local/cloud backend, `blob11` = route; `double1` = count, `double4` = latency ms, `double7` = estimated USD cost, `double9` = verifier-passed indicator.

Example SQL (Cloudflare Analytics Engine SQL API, using an **admin-only** Cloudflare token, never an embedded CLI token):

```sql
SELECT
  blob2 AS task_class,
  blob6 AS model_id,
  SUM(_sample_interval) AS attempts
FROM locdex_routing
WHERE timestamp > NOW() - INTERVAL '1' DAY
GROUP BY task_class, model_id
ORDER BY attempts DESC
LIMIT 20;
```

## 4. Operator safety before aggressive launch

- The Worker is a **public write-only telemetry endpoint**. Rate limiting is in the Worker, but you should also configure Cloudflare edge WAF/bot controls and monitor for poisoning/abuse.
- Set `PAUSE_INGESTION` to `1` in Wrangler config and redeploy to halt ingestion if abuse or a privacy incident occurs.
- Set R2 lifecycle/retention policies and account spending/billing alerts. Analytics Engine is not a substitute for retained, controlled research datasets.
- Cloudflare may process connection metadata (for example IPs) to deliver the HTTP request even though Locdex does not put those identifiers in the telemetry payload or R2 objects.
- A public endpoint cannot verify that every anonymous event genuinely came from a Locdex installation; reject poisoning statistically and do not treat production selection-biased outcomes as counterfactual benchmark data.
- Consider consent and privacy requirements for the jurisdictions where you distribute Locdex. The default-on BASIC setting is visible to users and reversible; RESEARCH requires a separate explicit enable.
- Never paste Cloudflare admin tokens or deploy credentials in a GitHub issue, README, or source file.
