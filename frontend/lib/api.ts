export class ApiError extends Error {
  constructor() {
    super("Không kết nối được với hệ thống. Mẹ thử lại sau nhé.");
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  try {
    const response = await fetch(`/api/backend/${path}`, { cache: "no-store" });
    if (!response.ok) throw new ApiError();
    return (await response.json()) as T;
  } catch {
    throw new ApiError();
  }
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  try {
    const response = await fetch(`/api/backend/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!response.ok) throw new ApiError();
    return (await response.json()) as T;
  } catch {
    throw new ApiError();
  }
}
