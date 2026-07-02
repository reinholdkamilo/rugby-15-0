# Rugby 15-0 Frontend

## Local Development

Start the FastAPI backend on `http://127.0.0.1:8000`, then run:

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000`.

## Cloudflare Mobile Testing

External devices cannot use the frontend default API URL
`http://127.0.0.1:8000`, because that points at the device itself. Use two
Cloudflare tunnels and start the frontend with the backend tunnel URL.

Terminal 1, backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Terminal 2, backend tunnel:

```bash
cloudflared tunnel --url http://localhost:8000
```

Copy the generated backend tunnel URL, for example
`https://backend-example.trycloudflare.com`.

Terminal 3, frontend:

```bash
cd frontend
NEXT_PUBLIC_API_BASE_URL=https://backend-example.trycloudflare.com npm run dev
```

Terminal 4, frontend tunnel:

```bash
cloudflared tunnel --url http://localhost:3000
```

Open the generated frontend tunnel URL on your phone. The frontend must be
started after setting `NEXT_PUBLIC_API_BASE_URL`; changing it requires restarting
`npm run dev`.
