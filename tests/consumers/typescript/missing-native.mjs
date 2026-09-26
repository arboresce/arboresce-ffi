import assert from "node:assert/strict";

await assert.rejects(import("arboresce"), /Cannot find native binding/);
