import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, apiGet, apiPost } from "../lib/api.ts";
import { backendAuthHeaders } from "../lib/backend-auth.ts";

test("server proxy attaches the Clerk bearer token only to backend headers", () => {
  const headers = backendAuthHeaders("session-token", true);
  assert.equal(headers.get("Authorization"), "Bearer session-token");
  assert.equal(headers.get("Content-Type"), "application/json");
});

test("API errors distinguish expired sessions and forbidden accounts", async () => {
  const previous = globalThis.fetch;
  try {
    for (const [status, expected] of [
      [401, "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."],
      [403, "Tài khoản này không có quyền sử dụng hệ thống."],
      [503, "Không kết nối được với hệ thống. Mẹ thử lại sau nhé."],
    ]) {
      globalThis.fetch = async () => new Response("{}", { status });
      await assert.rejects(apiGet("gardens"), (error) => error instanceof ApiError && error.message === expected);
      await assert.rejects(apiPost("assistant/chat", {}), (error) => error instanceof ApiError && error.message === expected);
    }
  } finally {
    globalThis.fetch = previous;
  }
});
