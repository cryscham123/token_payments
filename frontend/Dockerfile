FROM node:20-alpine

WORKDIR /workspace/frontend

COPY package*.json ./
RUN npm ci

COPY . .

# Produce the optimized production build. next.config uses output:"standalone", which emits
# a minimal self-contained server at .next/standalone/server.js. Static assets and public/
# are not bundled into it, so copy them next to the server.
RUN npm run build \
    && cp -r .next/static .next/standalone/.next/static \
    && cp -r public .next/standalone/public

EXPOSE 3000

ENV PORT=3000 HOSTNAME=0.0.0.0

CMD ["node", ".next/standalone/server.js"]
