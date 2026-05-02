# Workspace

## Overview

pnpm workspace monorepo using TypeScript + Python services for Bakong KHQR payment.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

---

## Bakong KHQR Payment API

Located in `bakong-api/` — Python FastAPI REST API.

### Files
- `bakong-api/main.py` — FastAPI application
- `bakong-api/requirements.txt` — Python dependencies

### Environment Variables
- `BAKONG_TOKEN` — Bakong NBC JWT token
- `KHQR_API_KEYS` — Comma-separated API key(s) for securing this API (X-API-Key header)

### Run
```bash
cd bakong-api && PORT=5000 python3 main.py
```

### Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc UI |
| POST | `/api/v1/generate-qr` | Generate KHQR QR code |
| POST | `/api/v1/check-payment` | Check payment status by MD5 |
| GET | `/api/v1/payment/{md5}` | Get paid transaction details |
| POST | `/api/v1/bulk-check` | Check up to 50 MD5s at once |
| POST | `/api/v1/deeplink` | Generate Bakong deep link |

### Authentication
All endpoints require `X-API-Key: <your-key>` header.

---

## Bakong KHQR Telegram Bot

Located in `telegram-bot/` — Python Telegram bot.

### Files
- `telegram-bot/bot.py` — main bot logic
- `telegram-bot/requirements.txt` — Python dependencies

### Environment Variables
- `BAKONG_TOKEN` — Bakong API JWT token
- `TELEGRAM_BOT_TOKEN` — Telegram bot token from @BotFather

### Commands
- `/start` — welcome menu
- `/pay` — generate KHQR QR code step by step
- `/check` — check payment status by MD5
- `/help` — usage guide
- `/cancel` — cancel current operation

### Run
```bash
cd telegram-bot && python3 bot.py
```
