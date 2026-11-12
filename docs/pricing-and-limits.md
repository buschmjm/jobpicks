# JobPicks pricing and usage limits

Pro is **$15/month**. Limits are designed so that even if we route all Pro AI traffic to a
frontier hosted model (OpenAI GPT-4o class pricing), worst-case API cost stays below **50% of
revenue** — leaving margin for Stripe fees, infra, and subsidized free-tier usage.

## Plans

| Feature | Free | Pro ($15/mo) |
| --- | --- | --- |
| Deck matches / day | 10 | All available ranked matches |
| Career advisor | 5 messages / day | 80 messages / month |
| Resume builder | 3 messages / day | 20 sessions / month |
| Application packets | 2 lifetime | 20 / month |
| Match explanations | 1 “why” bullet | Full breakdown + cautions |
| Intraday alerts | No | Yes |

On-demand paid top-ups for resume builds are planned but not wired yet.

## Cost model (frontier API worst case)

Reference pricing (OpenAI GPT-4o, rounded): **$2.50 / 1M input tokens**, **$10 / 1M output
tokens**.

Conservative per-action estimates at max configured limits:

| Action | Est. tokens (in → out) | Est. cost @ max Pro limit | Monthly max |
| --- | --- | --- | --- |
| Advisor message | 2,500 → 800 | ~$0.014 | 80 → **~$1.12** |
| Resume builder session | 4,000 → 1,500 | ~$0.025 | 20 → **~$0.50** |
| Application packet | 8,000 → 3,000 | ~$0.05 | 20 → **~$1.00** |

**Total estimated frontier API ceiling ≈ $2.62/month** per heavy Pro user (deck matching is
mostly embeddings/scoring, not chat completions).

We target **≤ $7.50** API spend per Pro user (50% of $15) before infra — roughly **2.9×** the
modeled worst case, leaving headroom for longer replies, tool calls, or a future switch from
self-hosted Ollama to hosted APIs.

## Implementation notes

- Limits live in `core/entitlements.py` and are enforced in `core/daily_usage.py` (free daily)
  and `core/monthly_usage.py` (pro monthly).
- Pro deck cap is unlimited (`PRO_DAILY_TOPUP_CAP = None`); the queue builder uses a high
  internal fallback when no cap is set.
- Stripe product: set `STRIPE_PRICE_ID_MONTHLY_1500` to the $15/mo price ID.

## URL layout

JobPicks is served at `https://app.willowriverautomation.com/jobpicks` (`APP_MOUNT_PATH=/jobpicks`).
Future WRA apps should follow the same pattern (`/moveanchor`, etc.) on the shared app host.
