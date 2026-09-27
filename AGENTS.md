# Vineyard Management Project

## Tech stack

- Frontend: Next.js
- Backend: Python + FastAPI
- Database: Neon PostgreSQL
- ORM: SQLAlchemy 2.x
- Migration: Alembic
- AI: Gemini 3.x Flash - chuyển model mỗi khi hết quota

## Architecture rules

- Frontend must not connect directly to PostgreSQL.
- Frontend must not expose Gemini API keys.
- FastAPI is the main backend layer.
- Gemini must never write SQL directly.
- AI output must be validated by backend business rules.
- Financial write operations initiated by AI must require user confirmation before persisting.

## Database rules

- Reuse the existing SQLAlchemy Base and engine.
- Use Alembic for schema changes.
- Do not duplicate financial records.
- Customer debt = sales - customer payments.
- Worker debt = labor records - worker payments.

## Current scope

Modules:

- Gardens
- Seasons
- Grape varieties
- Harvests
- Wholesale customers
- Customer payments
- Workers
- Labor records
- Worker payments
- Expenses
- Reports
- AI assistant

Do not add extra modules unless explicitly requested.

## Coding rules

- Keep code simple and MVP-oriented.
- Use Python type hints.
- Use SQLAlchemy 2.x Mapped / mapped_column style.
- Keep API routes thin.
- Never expose secrets from .env files.
- Read existing code before creating new files or abstractions.

## Agent workflow

Before modifying code:

1. Inspect the repository structure.
2. Use Serena for code navigation and symbol lookup.
3. Use Context7 when current framework documentation is needed.
4. Use Neon MCP for Neon-related operations.
5. Run relevant validation/tests after changes.
6. Report files changed and unresolved issues.
