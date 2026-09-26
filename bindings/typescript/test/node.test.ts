import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { Worker } from "node:worker_threads";
import { NAME, name } from "arboresce";

test("public identity", () => {
  assert.equal(NAME, "Arboresce");
  assert.equal(name(), "Arboresce");
});

test("repeated calls", () => {
  for (let i = 0; i < 1000; i++) assert.equal(name(), "Arboresce");
});

test("concurrent native calls", { timeout: 20000 }, async () => {
  await Promise.all(
    Array.from(
      { length: 8 },
      () =>
        new Promise<void>((resolve, reject) => {
          const worker = new Worker(
            new URL("./fixtures/worker.js", import.meta.url),
          );
          let received = false;
          worker.once("error", reject);
          worker.once("message", (values) => {
            try {
              assert.deepEqual(values, Array(128).fill("Arboresce"));
              received = true;
            } catch (error) {
              reject(error);
            }
          });
          worker.once("exit", (code) =>
            code === 0 && received
              ? resolve()
              : reject(new Error(`worker exited ${code}`)),
          );
        }),
    ),
  );
});

test("native print output", () => {
  const helper = fileURLToPath(
    new URL("./fixtures/print-name.js", import.meta.url),
  );
  assert.equal(
    execFileSync(process.execPath, [helper], {
      encoding: "utf8",
      timeout: 20000,
    }),
    "Arboresce\n",
  );
});
