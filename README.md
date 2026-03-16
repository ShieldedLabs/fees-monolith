# Dynamic Fees Monolith

This repository aggregates several Zcash-related projects as git subtrees for dynamic fee research and development.

## Subtrees

| Directory | Upstream | Branch |
|-----------|----------|--------|
| `zaino/` | [zingolabs/zaino](https://github.com/zingolabs/zaino) | `dev` |
| `zips/` | [zcash/zips](https://github.com/zcash/zips) | `main` |
| `fee-calculator/` | [ShieldedLabs/fee-playground](https://github.com/ShieldedLabs/fee-playground) | `main` |

## Subtree Commands

### Pull upstream changes

```bash
git subtree pull --prefix=zaino --squash zaino dev
git subtree pull --prefix=zips --squash zips main
git subtree pull --prefix=fee-calculator --squash fee-calculator main
```

### Push changes upstream

```bash
git subtree push --prefix=zaino zaino dev
git subtree push --prefix=zips zips main
git subtree push --prefix=fee-calculator fee-calculator main
```
