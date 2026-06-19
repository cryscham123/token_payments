const fs = require("node:fs");
const path = require("node:path");

const RPC_URL = process.env.TEST_NETWORK_RPC_URL || "http://127.0.0.1:8545";
const DB_PATH = process.env.TEST_NETWORK_DB_PATH || "/var/chainDB";
const DEPLOYER = process.env.TEST_NETWORK_ACCOUNT;

// Precompiled minimal ERC-20-like runtime for local tests. transfer(address,uint256)
// emits a standard Transfer log and returns true; no balances are enforced.
const MINIMAL_ERC20_BYTECODE =
  "0x608060405234801561000f575f80fd5b5061042c8061001d5f395ff3fe608060405234801561000f575f80fd5b5060043610610034575f3560e01c806370a0823114610038578063a9059cbb14610068575b5f80fd5b610052600480360381019061004d919061029f565b610098565b60405161005f91906102e2565b60405180910390f35b610082600480360381019061007d9190610325565b6100ac565b60405161008f919061037d565b60405180910390f35b5f602052805f5260405f205f915090505481565b5f815f803373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f20541061013e57815f803373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205f8282540392505081905550610180565b5f805f3373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f20819055505b815f808573ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205f8282546101cb91906103c3565b925050819055508273ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff167fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef8460405161022f91906102e2565b60405180910390a36001905092915050565b5f80fd5b5f73ffffffffffffffffffffffffffffffffffffffff82169050919050565b5f61026e82610245565b9050919050565b61027e81610264565b8114610288575f80fd5b50565b5f8135905061029981610275565b92915050565b5f602082840312156102b4576102b3610241565b5b5f6102c18482850161028b565b91505092915050565b5f819050919050565b6102dc816102ca565b82525050565b5f6020820190506102f55f8301846102d3565b92915050565b610304816102ca565b811461030e575f80fd5b50565b5f8135905061031f816102fb565b92915050565b5f806040838503121561033b5761033a610241565b5b5f6103488582860161028b565b925050602061035985828601610311565b9150509250929050565b5f8115159050919050565b61037781610363565b82525050565b5f6020820190506103905f83018461036e565b92915050567f4e487b71000000000000000000000000000000000000000000000000000000005f52601160045260245ffd5b5f6103cd826102ca565b91506103d8836102ca565b92508282019050808211156103f0576103ef610396565b5b9291505056fea26469706673582212204e7be7dff7cb95ff8589ea70aa9b63dc917deb9c130f12d51111727fee2abf2a64736f6c63430008140033";

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
