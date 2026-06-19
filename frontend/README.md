# Token Payments Web

Next.js + React + Tailwind CSS customer storefront for the Token Payments local stack.

The first component set was imported from `https://github.com/joonistaa/ethercommerce` at commit `69596a5ef735d2c84739ac58d4ce747bc1996cf0`. That repository currently contains standalone JSX screen components, so this directory adds the Next.js application shell, Tailwind configuration, Docker runtime, and route wiring.

```bash
cd frontend
npm ci
npm run dev -- --hostname 0.0.0.0 --port 3000
```

In Docker Compose, nginx routes public storefront traffic to `token_payments_web:3000` and routes API paths to `token_payments_api:8000`. Browser auth uses same-origin relative paths: `POST /auth/challenges`, MetaMask `personal_sign`, then `POST /auth/sessions` with cookie credentials.
