export class ApiError extends Error {
  constructor(status?: number) {
    super(status === 401 ? "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại." : status === 403 ? "Tài khoản này không có quyền sử dụng hệ thống." : "Không kết nối được với hệ thống. Mẹ thử lại sau nhé.");
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  try {
    const response = await fetch(`/api/backend/${path}`, { cache: "no-store" });
    if (!response.ok) throw new ApiError(response.status);
    return (await response.json()) as T;
  } catch (error) {
    throw error instanceof ApiError ? error : new ApiError();
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
    if (!response.ok) throw new ApiError(response.status);
    return (await response.json()) as T;
  } catch (error) {
    throw error instanceof ApiError ? error : new ApiError();
  }
}
