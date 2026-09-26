import assert from "node:assert/strict";

Object.defineProperty(process, "platform", { value: "arboresce-unsupported" });
await assert.rejects(import("arboresce"), (error) => {
  assert.match(error.message, /Cannot find native binding/);
  let cause = error.cause;
  while (cause && !cause.message.includes("Unsupported OS"))
    cause = cause.cause;
  assert.match(cause?.message ?? "", /Unsupported OS: arboresce-unsupported/);
  return true;
});
