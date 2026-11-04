# Run Locally
```bash
cp .env.example .env                       # optional ANTHROPIC_API_KEY
cd apps/api && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --port 8000
cd apps/web && npm install && echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" > .env.local && npm run dev
./scripts/dev-swarm.sh                     # tmux: agents feed | API | web  (stop: ./scripts/dev-swarm.sh stop)
```
Without a key every agent shows "Deterministic". Real students need their browser token or get 404 ([[Auth & Privacy]]).
