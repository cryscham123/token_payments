FROM node:alpine

WORKDIR /app

RUN npm install -g ganache
ENV NODE_OPTIONS "--no-warnings"

CMD ganache \
	-h 0.0.0.0 \
	--wallet.accounts ${TEST_NETWORK_PRIVATE_KEY},0x1000000000000000000 \
	--miner.coinbase ${TEST_NETWORK_ACCOUNT} \
	--database.dbPath ${TEST_NETWORK_DB_PATH} \
	--chain.networkId ${TEST_NETWORK_NETWORK_ID} \
	--chain.asyncRequestProcessing
