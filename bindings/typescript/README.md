# Arboresce TypeScript SDK

TypeScript SDK for Arboresce.

```bash
npm install arboresce
```

```ts
import { name, printName } from "arboresce";

console.assert(name() === "Arboresce");
printName();
```

For browsers, use the WebAssembly entry point and initialize it before calling
the API:

```ts
import { initialize, name, printName } from "arboresce/browser";

await initialize();
console.assert(name() === "Arboresce");
printName();
```

Serve the generated `.wasm` asset alongside its JavaScript module. Browser
initialization accepts an explicit module or URL when the application serves
the asset elsewhere. This entry point uses browser WebAssembly, not WASI.

## Source layout

| Directory | Ownership |
| --- | --- |
| `src/` | Handwritten TypeScript public entry points |
| `native/` | napi-rs generated Node loader and declarations; ignored local `.node` binaries |
| `wasm/` | wasm-bindgen generated browser glue and declarations; ignored `.wasm` binary and packaging metadata |
| `test/` | Node API tests, WASM tests under Node, Chromium browser tests, fixtures and consumer type checks |
| `dist/` | Ignored compiled JavaScript and declarations |

Generated source is maintained through the pinned generators, never edited by
hand. Platform npm packages are generated into the SDK's ignored
`build/typescript/npm/<platform-arch-abi>/` staging directory. Their package
names remain `@arboresce/native-<platform-arch-abi>`; only active targets are
generated. Local archives are written to `build/dist/npm/` at the SDK root.

See the repository's `DEVELOPERS.md` for prerequisites and Make commands.
