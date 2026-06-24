FROM node:alpine

WORKDIR /app

RUN npm install -g ganache
ENV NODE_OPTIONS "--no-warnings"
COPY deploy.js /app/deploy.js

CMD ["sh", "-c", "ganache -h 0.0.0.0 --wallet.accounts ${TEST_NETWORK_PRIVATE_KEY},0x1000000000000000000 --wallet.accounts 0x6c29146783d558055c7c59802761d224003097f57a986d349696b9d70c440d95,0x1000000000000000000 --miner.coinbase ${TEST_NETWORK_ACCOUNT} --database.dbPath ${TEST_NETWORK_DB_PATH} --chain.networkId ${TEST_NETWORK_NETWORK_ID} --chain.asyncRequestProcessing & GANACHE_PID=$!; node /app/deploy.js; wait $GANACHE_PID"]
