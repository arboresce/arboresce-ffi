import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { initialize, name, printName } from "arboresce/browser";

test("browser API contract", async (t) => {
  await t.test("requires initialization", () => assert.throws(() => name()));
  await assert.rejects(initialize({ module_or_path: new Uint8Array([0]) }));
  const input = {
    module_or_path: await readFile(
      new URL(
        "../wasm/arboresce_wasm_bg.wasm",
        import.meta.resolve("arboresce/browser"),
      ),
    ),
  };
  const first = initialize(input);
  const second = initialize(input);
  assert.equal(first, second);
  const output = await first;
  assert.equal(await initialize(), output);
  await t.test("public identity", () => assert.equal(name(), "Arboresce"));
  await t.test("repeated calls", () => {
    for (let i = 0; i < 1000; i++) assert.equal(name(), "Arboresce");
  });
  await t.test("concurrent callers", async () => {
    const values = await Promise.all(
      Array.from({ length: 8 }, async () =>
        Array.from({ length: 128 }, () => name()),
      ),
    );
    for (const group of values)
      assert.deepEqual(group, Array(128).fill("Arboresce"));
  });
  await t.test("print output", (t) => {
    const log = t.mock.method(console, "log", () => undefined);
    printName();
    assert.equal(log.mock.callCount(), 1);
    assert.deepEqual(log.mock.calls[0].arguments, ["Arboresce"]);
  });
});
