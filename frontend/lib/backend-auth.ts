/** Headers used only by the server-side FastAPI proxy. */
export function backendAuthHeaders(token: string, hasBody: boolean): Headers {
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  if (hasBody) headers.set("Content-Type", "application/json");
  return headers;
}
