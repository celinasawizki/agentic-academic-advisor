# Shared contracts

The API's Pydantic models (`apps/api/app/domain.py`, request bodies in `apps/api/app/routers/*.py`) are the source of truth. The web app mirrors them in `apps/web/src/lib/types.ts`.

Live JSON Schema for every request/response is served by FastAPI at `GET /openapi.json` (interactive docs at `/docs`). To generate TypeScript types from it:

```bash
npx openapi-typescript http://127.0.0.1:8000/openapi.json -o packages/shared/api.d.ts
```
