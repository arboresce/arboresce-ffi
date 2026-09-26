import initializeWasm, { name as wasmName } from "../wasm/arboresce_wasm.js";

let initialization: ReturnType<typeof initializeWasm> | undefined;
let ready = false;

export function initialize(
  input?: Parameters<typeof initializeWasm>[0],
): ReturnType<typeof initializeWasm> {
  if (initialization === undefined) {
    initialization = initializeWasm(input).then(
      (output) => {
        ready = true;
        return output;
      },
      (error: unknown) => {
        initialization = undefined;
        throw error;
      },
    );
  }
  return initialization;
}

export function name(): string {
  if (!ready)
    throw new Error("Arboresce is not initialized; await initialize()");
  return wasmName();
}

export function printName(): void {
  console.log(name());
}
