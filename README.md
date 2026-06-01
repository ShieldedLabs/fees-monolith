# Dynamic Fees Monolith

This repository aggregates several Zcash-related projects as git subtrees for dynamic fee research and development.

## Architecture

The `z_getstandardfee` fee estimation algorithm lives in **zebrad** (the full node). Both indexers proxy to it:

- **Zaino** exposes it as a JSON-RPC method (`z_getstandardfee`) by proxying to zebrad.
- **lightwalletd** exposes it as a gRPC method (`GetStandardFee`) by proxying to zebrad.

## Subtrees

| Directory | Upstream | Branch |
|-----------|----------|--------|
| `zebra/` | [ShieldedLabs/zebra-dynamic-fees](https://github.com/ShieldedLabs/zebra-dynamic-fees) | `aphelionz/z_getstandardfee` |
| `zaino/` | [zingolabs/zaino](https://github.com/zingolabs/zaino) | `dev` |
| `lightwalletd/` | [zcash/lightwalletd](https://github.com/zcash/lightwalletd) | `master` |
| `zips/` | [zcash/zips](https://github.com/zcash/zips) | `main` |
| `fee-calculator/` | [ShieldedLabs/fee-playground](https://github.com/ShieldedLabs/fee-playground) | `main` |

## Docker Compose

Assumes zebrad is running on the `zcash_default` Docker network.

```bash
docker compose build
docker compose up -d

# Zaino JSON-RPC
curl -X POST http://127.0.0.1:18088 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"z_getstandardfee","id":1}'

# lightwalletd gRPC
grpcurl -plaintext localhost:19067 \
  cash.z.wallet.sdk.rpc.CompactTxStreamer/GetStandardFee
```

## Subtree Commands

### Pull upstream changes

```bash
git subtree pull --prefix=zebra https://github.com/ShieldedLabs/zebra-dynamic-fees.git aphelionz/z_getstandardfee --squash
git subtree pull --prefix=zaino https://github.com/zingolabs/zaino.git dev --squash
git subtree pull --prefix=lightwalletd https://github.com/zcash/lightwalletd.git master --squash
git subtree pull --prefix=zips https://github.com/zcash/zips.git main --squash
git subtree pull --prefix=fee-calculator https://github.com/ShieldedLabs/fee-playground.git main --squash
```
