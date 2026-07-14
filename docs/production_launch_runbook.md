# CA Copilot Production Launch Runbook

This runbook turns the local/beta build into a sellable production deployment. The app now has provider-ready adapters for email, Razorpay payments, Sentry, Prometheus metrics, Meta WhatsApp, Azure Document Intelligence, and OpenAI/Anthropic AI.

## 1. Required Accounts

Create these accounts before launch:

- SMTP provider: AWS SES, SendGrid, Mailgun, Zoho SMTP, or another transactional SMTP service.
- Razorpay: live account with KYC completed, payment links enabled, and webhook secret generated.
- Sentry: backend project DSN.
- Cloud: AWS account with RDS Postgres, ElastiCache Redis, S3, Secrets Manager, ECS/Fargate or equivalent.
- Meta WhatsApp Business: phone number ID, permanent access token, and webhook verify token.
- Azure Document Intelligence: endpoint and key.
- AI: OpenAI API key and/or Anthropic API key.

## 2. Production Secrets

Copy `backend/.env.production.example` to `backend/.env.production` only for local production rehearsal. In cloud, store the same values in your secret manager.

Minimum required values:

- `DATABASE_URL`: managed Postgres connection string.
- `REDIS_URL`: managed Redis connection string.
- `SECRET_KEY`: 64-byte random secret.
- `S3_BUCKET`, `AWS_REGION`: production document bucket.
- `FRONTEND_URL`: public app URL.
- `TRUSTED_HOSTS`: public frontend and API hostnames.
- `EMAIL_PROVIDER=smtp`, `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`.
- `PAYMENT_PROVIDER=razorpay`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`.
- `SENTRY_DSN`, `METRICS_BEARER_TOKEN`.
- `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN`.
- `AZURE_DOC_ENDPOINT`, `AZURE_DOC_KEY`.
- `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`.

## 3. DNS And TLS

Create DNS records:

- `app.yourdomain.com` -> frontend.
- `api.yourdomain.com` -> backend.
- Optional: `metrics.yourdomain.com` only if your monitoring stack needs a separate route.

Enable TLS at the load balancer or reverse proxy. Set `ENV=production` so backend HSTS is enabled.

## 4. Managed Data Services

Use managed services before taking real customers:

- Postgres 16 with pgvector enabled.
- Automated daily backups and point-in-time recovery.
- Redis with auth enabled and private networking.
- S3 bucket with block public access, lifecycle retention, and encryption.

Run migrations during deploy:

```bash
cd backend
alembic upgrade head
```

## 5. Email Setup

Verify sender domain and SPF/DKIM/DMARC with the SMTP provider.

Smoke test:

```bash
curl -X POST https://api.yourdomain.com/auth/password-reset/request \
  -H "Content-Type: application/json" \
  -d '{"email":"real-user@yourdomain.com"}'
```

Expected result: the user receives a reset email linking to `/reset-password?token=...`.

## 6. Razorpay Setup

In Razorpay dashboard:

- Add webhook URL: `https://api.yourdomain.com/billing/webhooks/razorpay`
- Subscribe to `payment_link.paid` and `payment.captured`.
- Copy the webhook secret into `RAZORPAY_WEBHOOK_SECRET`.

Smoke test:

1. Create an invoice in Billing.
2. Click `Checkout`.
3. Pay with Razorpay test/live mode as applicable.
4. Confirm a receipt appears and the invoice status becomes `paid` or `part_paid`.

## 7. Observability

Set:

- `SENTRY_DSN`
- `SENTRY_TRACES_SAMPLE_RATE`
- `METRICS_ENABLED=true`
- `METRICS_BEARER_TOKEN`

Prometheus scrape path:

```text
GET /metrics
Authorization: Bearer <METRICS_BEARER_TOKEN>
```

Recommended alerts:

- API 5xx rate above 1% for 5 minutes.
- P95 latency above 1.5 seconds for 10 minutes.
- Celery queue age above 5 minutes.
- OCR failure rate above 5%.
- WhatsApp send failure rate above 5%.
- Postgres storage above 80%.
- Redis memory above 80%.

## 8. Real Integration Setup

WhatsApp:

- Configure Meta webhook URL: `https://api.yourdomain.com/whatsapp/webhook`
- Set verify token to `WHATSAPP_VERIFY_TOKEN`.
- Use approved templates for proactive reminders.

OCR:

- Set `AZURE_DOC_ENDPOINT` and `AZURE_DOC_KEY`.
- Upload a real invoice and confirm document status reaches `processed` or `verified`.

AI:

- Set `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY`.
- Build the legal knowledge base with `backend/scripts/build_legal_kb.py`.
- Run a notice draft and confirm sources/citation validation are present before CA approval.

## 9. Release Gates

Every production release must pass:

```bash
docker compose exec -T backend pytest -q
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:e2e
python artifacts/live_api_2000_regression.py
```

In GitHub Actions, the same gates are wired in `.github/workflows/quality.yml`.

## 10. Go-Live Checklist

- No development secrets in deployed compose/task definitions.
- `ENV=production`.
- `TRUSTED_HOSTS` matches production hostnames.
- Frontend uses `NEXT_PUBLIC_API_URL=https://api.yourdomain.com`.
- Reset and verification emails arrive in inbox.
- Razorpay webhook records payments.
- `/diagnostics` shows no unexpected fallback modes.
- Backups are enabled and restore has been tested.
- Sentry receives backend errors.
- Prometheus can scrape `/metrics`.
- Playwright browser regression passes against staging.
