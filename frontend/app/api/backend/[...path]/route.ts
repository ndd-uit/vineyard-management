const readPaths = new Set([
  "reports/overview",
  "reports/customer-receivables",
  "reports/worker-payables",
  "gardens",
  "grape-varieties",
  "seasons",
  "harvests",
  "customers",
  "workers",
  "sales",
  "expenses",
]);

function backendUrl(path: string): URL {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  return new URL(`/api/${path}`, base);
}

async function forward(path: string, method: "GET" | "POST", body?: string): Promise<Response> {
  try {
    const upstream = await fetch(backendUrl(path), {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  } catch {
    return Response.json({ detail: "Không kết nối được với hệ thống." }, { status: 503 });
  }
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(_request: Request, context: RouteContext): Promise<Response> {
  const path = (await context.params).path.join("/");
  if (!readPaths.has(path)) return Response.json({ detail: "Không tìm thấy." }, { status: 404 });
  return forward(path, "GET");
}

export async function POST(request: Request, context: RouteContext): Promise<Response> {
  const path = (await context.params).path.join("/");
  if (path !== "assistant/chat") return Response.json({ detail: "Không tìm thấy." }, { status: 404 });
  return forward(path, "POST", await request.text());
}
