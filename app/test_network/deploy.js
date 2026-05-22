const fs = require("node:fs");
const path = require("node:path");

const RPC_URL = process.env.TEST_NETWORK_RPC_URL || "http://127.0.0.1:8545";
const DB_PATH = process.env.TEST_NETWORK_DB_PATH || "/var/chainDB";
const DEPLOYER = process.env.TEST_NETWORK_ACCOUNT;

// Precompiled minimal ERC-20-like runtime for local tests. transfer(address,uint256)
// emits a standard Transfer log and returns true; no balances are enforced.
const MINIMAL_ERC20_BYTECODE =
  "0x604f600c600039604f6000f360003560e01c63a9059cbb1460145760006000f35b602435600052600435337fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef60206000a3600160005260206000f3";

async function rpc(method, params = []) {
  const response = await fetch(RPC_URL, {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({jsonrpc: "2.0", id: 1, method, params}),
  });
  const payload = await response.json();
  if (payload.error) {
    throw new Error(`${method} failed: ${JSON.stringify(payload.error)}`);
  }
  return payload.result;
}

async function waitForRpc() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      await rpc("eth_chainId");
      return;
    } catch (_error) {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  throw new Error("Ganache RPC did not become ready");
}

async function deployToken(symbol) {
  const txHash = await rpc("eth_sendTransaction", [
    {
      from: DEPLOYER,
      data: MINIMAL_ERC20_BYTECODE,
      gas: "0x2dc6c0",
    },
  ]);
  const receipt = await rpc("eth_getTransactionReceipt", [txHash]);
  if (!receipt || !receipt.contractAddress) {
    throw new Error(`${symbol} deployment did not produce a contract address`);
  }
  return {
    symbol,
    decimals: 6,
    address: receipt.contractAddress,
    deploymentTxHash: txHash,
  };
}

async function main() {
  if (!DEPLOYER) {
    throw new Error("TEST_NETWORK_ACCOUNT is required to deploy local ERC-20 fixtures");
  }
  await waitForRpc();
  const chainId = await rpc("eth_chainId");
  const deployed = {
    chainId: Number.parseInt(chainId, 16),
    assets: {
      USDC: await deployToken("USDC"),
      USDT: await deployToken("USDT"),
    },
  };
  fs.mkdirSync(DB_PATH, {recursive: true});
  fs.writeFileSync(path.join(DB_PATH, "deployed_contracts.json"), JSON.stringify(deployed, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
