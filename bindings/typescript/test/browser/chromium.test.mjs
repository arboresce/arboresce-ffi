import { chromium } from "playwright";
import test from "node:test";

import { createServer } from "node:http";
import { appendFile, readFile } from "node:fs/promises";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { resolve, sep } from "node:path";
import assert from "node:assert/strict";

test("Chromium browser API contract", { timeout: 30000 }, async (t) => {
  const root = fileURLToPath(
    new URL("../", import.meta.resolve("arboresce/browser")),
  );
  const server = createServer(async (request, response) => {
    if (request.url === "/") {
      response.setHeader("Content-Type", "text/html");
      response.end("<!doctype html><title>Arboresce browser consumer</title>");
      return;
    }
    if (request.url === "/favicon.ico") {
      response.writeHead(204).end();
      return;
    }
    const path = resolve(
      root,
      "." + new URL(request.url, "http://localhost").pathname,
    );
    if (!path.startsWith(root.endsWith(sep) ? root : root + sep)) {
      response.writeHead(403).end();
      return;
    }
    try {
      response.setHeader(
        "Content-Type",
        path.endsWith(".wasm") ? "application/wasm" : "text/javascript",
      );
      response.end(await readFile(path));
    } catch {
      response.writeHead(404).end();
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    const messages = [];
    page.on("console", (message) => messages.push(message.text()));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await t.test("requires initialization", async () => {
      assert.equal(
        await page.evaluate(async () => {
          const sdk = await import("/dist/browser.js");
          try {
            sdk.name();
            return false;
          } catch {
            return true;
          }
        }),
        true,
      );
    });
    await t.test(
      "initialization retries and shares concurrent work",
      async () => {
        assert.equal(
          await page.evaluate(async () => {
            const sdk = await import("/dist/browser.js");
            let rejected = false;
            try {
              await sdk.initialize({ module_or_path: new Uint8Array([0]) });
            } catch {
              rejected = true;
            }
            const first = sdk.initialize();
            const second = sdk.initialize();
            const output = await first;
            return (
              rejected &&
              first === second &&
              (await sdk.initialize()) === output
            );
          }),
          true,
        );
      },
    );
    await t.test("public identity", async () => {
      assert.equal(
        await page.evaluate(async () =>
          (await import("/dist/browser.js")).name(),
        ),
        "Arboresce",
      );
    });
    await t.test("repeated calls", async () => {
      assert.deepEqual(
        await page.evaluate(async () => {
          const sdk = await import("/dist/browser.js");
          return Array.from({ length: 1000 }, () => sdk.name());
        }),
        Array(1000).fill("Arboresce"),
      );
    });
    await t.test("concurrent callers", async () => {
      const groups = await page.evaluate(async () => {
        const sdk = await import("/dist/browser.js");
        return Promise.all(
          Array.from({ length: 8 }, async () =>
            Array.from({ length: 128 }, () => sdk.name()),
          ),
        );
      });
      assert.deepEqual(
        groups,
        Array.from({ length: 8 }, () => Array(128).fill("Arboresce")),
      );
    });
    await t.test("print output", async () => {
      messages.length = 0;
      await page.evaluate(async () =>
        (await import("/dist/browser.js")).printName(),
      );
      assert.deepEqual(messages, ["Arboresce"]);
    });
    if (process.env.ARBORESCE_TEST_EVIDENCE && !t.signal.aborted) {
      const architecture = { arm64: "arm64", x64: "x64" }[os.arch()];
      assert.ok(architecture, "Unsupported browser host architecture");
      const entry = {
        schema: 1,
        language: "typescript",
        target: "browser",
        execution: "browser",
        architecture,
        host: `${os.type()} ${os.release()}`,
        runtime: { chromium: browser.version() },
        minimum_runtime: false,
        suite: process.env.ARBORESCE_TEST_SUITE || "public",
      };
      await appendFile(
        process.env.ARBORESCE_TEST_EVIDENCE,
        JSON.stringify(entry) + "\n",
      );
    }
  } finally {
    await browser?.close();
    await new Promise((resolve) => server.close(resolve));
  }
});
