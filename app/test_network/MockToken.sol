// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Minimal standard ERC-20 for the local test network. The deployer (TEST_NETWORK_ACCOUNT)
// receives the entire supply in the constructor, so the faucet's `transfer(user, amount)`
// from the deployer works like a normal ERC-20 transfer. Used for both USDC and USDT
// fixtures (6 decimals); name/symbol are cosmetic since the app reads its own asset registry.
contract MockToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 6;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    // name/symbol are passed per token (e.g. "USD Coin"/"USDC") so MetaMask's wallet_watchAsset
    // symbol check against the on-chain symbol() passes.
    constructor(string memory _name, string memory _symbol) {
        name = _name;
        symbol = _symbol;
        uint256 supply = 1_000_000_000_000 * (10 ** uint256(decimals)); // 1e12 tokens
        totalSupply = supply;
        balanceOf[msg.sender] = supply;
        emit Transfer(address(0), msg.sender, supply);
    }

    function transfer(address to, uint256 value) external returns (bool) {
        require(balanceOf[msg.sender] >= value, "insufficient balance");
        balanceOf[msg.sender] -= value;
        balanceOf[to] += value;
        emit Transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        require(balanceOf[from] >= value, "insufficient balance");
        require(allowance[from][msg.sender] >= value, "insufficient allowance");
        allowance[from][msg.sender] -= value;
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
        return true;
    }
}
