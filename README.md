# Preview environments proof of concept

A small TypeScript frontend and Python API for exercising image builds, browser
checks, database migrations and progressive delivery. This first step runs
locally; AKS preview and release configuration will follow in separate PRs.

## Run locally

```sh
docker compose up --build -d
```

Open <http://localhost:8080>, select **Check API**, and confirm the response.
The frontend proxies `/api/` to the Python service. Check API health at
<http://localhost:8080/api/healthz>.

Run the browser smoke test:

```sh
cd frontend
npm ci
npx playwright install chromium
npm test
```

Stop the services with `docker compose down`. Playwright is a frontend
development dependency, not part of either runtime image. The same test can run
in a Testkube browser container once the PR preview exists.

The frontend uses `package-lock.json`. The backend keeps its direct and
transitive dependency versions together in `backend/requirements.txt`.
