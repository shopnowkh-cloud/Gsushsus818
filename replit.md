# Workspace

## Overview

pnpm workspace monorepo using TypeScript + a Python Telegram bot for Bakong KHQR payment.

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

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.

## Telegram Bot (Bakong KHQR)

Located in `telegram-bot/` — a standalone Python bot.

### Files
- `telegram-bot/bot.py` — main bot logic
- `telegram-bot/requirements.txt` — Python dependencies

### Environment Variables
- `BAKONG_TOKEN` — Bakong API JWT token
- `TELEGRAM_BOT_TOKEN` — Telegram bot token from @BotFather

### Features
- `/start` — welcome menu with inline buttons
- `/pay` — step-by-step flow to generate a Bakong KHQR QR code (account, name, city, amount, currency, bill number)
- `/check` — check payment status by MD5 hash
- `/help` — usage guide
- `/cancel` — cancel current operation
- Inline payment status check button on each generated QR
- Supports USD and KHR currencies
- Generates styled KHQR PNG image + Bakong deep link

### Run
```bash
cd telegram-bot && python3 bot.py
```
