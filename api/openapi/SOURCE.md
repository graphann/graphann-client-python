# Vendored OpenAPI spec

`spec.yaml` in this directory is a **copy** of `api/openapi/spec.yaml` from the graphann
server repository. It is the single input every client SDK generates from.

| | |
|---|---|
| Source repo | `graphann` |
| Source path | `api/openapi/spec.yaml` |
| Vendored from commit | `f313b4b` |
| Vendored on | 2026-09-07 |
| sha256 | `54bfd746362462ee4f2b0bb16d3e368c…` (first 32 chars) |
| Lines | 4493 |

## Why it is vendored rather than referenced

Each SDK ships a staleness check that regenerates its types and byte-compares the result
against what is committed. Those checks need the spec to exist. Referencing the server
repo by absolute path made every check pass **by skipping** on any machine that was not
the author's laptop — which is the same failure as no check at all, only harder to notice.

Vendoring makes each SDK self-contained: the checks run on a fresh clone and in CI, and the
diff shows exactly which spec revision each SDK was generated against.

## Updating

When the server's spec changes:

```sh
./scripts/vendor-spec.sh /path/to/graphann     # refresh spec.yaml + this file
# then regenerate each SDK and commit the result:
cd typescript && npm run gen:types
cd go         && ./scripts/generate-types.sh
cd python     && ./scripts/generate_types.sh
cd rust       && cargo run -p graphann-codegen
```

Each SDK's staleness check will fail until its generated file is regenerated and committed,
which is the point.

## What this does NOT guarantee

Nothing here proves the vendored copy still matches upstream — only that each SDK matches
the vendored copy. Drift between this file and the server is caught by re-running
`vendor-spec.sh` and seeing a non-empty diff. The server side has its own guarantee that
the spec matches the code: `TestSpecCoversAllRegisteredRoutes` (routes) and
`TestSpecSchemasMatchGoStructs` (schemas) in `internal/server`.
