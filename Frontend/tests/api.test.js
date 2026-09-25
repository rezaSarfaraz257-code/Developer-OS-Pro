import test from "node:test";
import assert from "node:assert/strict";

function safeExternalUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

test("safeExternalUrl accepts http and https URLs", () => {
  assert.equal(safeExternalUrl("https://example.com/path"), "https://example.com/path");
  assert.equal(safeExternalUrl("http://localhost:5173"), "http://localhost:5173/");
});

test("safeExternalUrl rejects dangerous or malformed URLs", () => {
  assert.equal(safeExternalUrl("javascript:alert(1)"), null);
  assert.equal(safeExternalUrl("data:text/html,test"), null);
  assert.equal(safeExternalUrl("not-a-url"), null);
  assert.equal(safeExternalUrl(""), null);
});
