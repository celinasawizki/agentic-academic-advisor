# Refresh Temple Data
**Ask the project owner before any network refresh.**
```bash
cd apps/api
python -m scripts.ingest_bulletin            # re-parse from cache, no network (use after parser changes)
python -m scripts.ingest_bulletin --refresh  # ~20 min at 1 req/s
python -m scripts.import_sections 202703     # section snapshot — only with permission
```
Rules: robots.txt, 1 req/s, identifying UA, cache in `data/temple/.cache` (gitignored, not redistributed). Never scrape Google; bulletin search is robots-disallowed. See [[Temple Data Snapshot]].
