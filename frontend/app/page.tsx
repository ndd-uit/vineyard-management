"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import StatCard from "@/components/dashboard/StatCard";
import { PageGrapeLoader } from "@/components/ui/GrapeLoaders";
import { ApiError, apiGet } from "@/lib/api";
import { formatKg, formatMoney } from "@/lib/format";
import type { Overview } from "@/types/api";

export default function Home() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<Overview>("reports/overview").then(setOverview).catch((cause) => setError(cause instanceof ApiError ? cause.message : new ApiError().message));
  }, []);

  return (
    <div className="page-stack">
      <section className="hero-card">
        <div>
          <span className="eyebrow">SỔ TAY VƯỜN NHO</span>
          <h1>Chào mẹ, hôm nay mình xem gì ạ?</h1>
          <p>Thu hoạch, bán nho và các khoản thu chi đều ở đây, dễ xem bất cứ lúc nào.</p>
          <Link className="button button-primary" href="/assistant">Trò chuyện với trợ lý</Link>
        </div>
        <div className="hero-art" aria-hidden="true"><Image src="/grape-logo.png" alt="" width={240} height={240} priority /></div>
      </section>

      <section aria-labelledby="overview-title">
        <div className="section-heading"><div><span className="eyebrow">NHÌN NHANH</span><h2 id="overview-title">Tình hình vườn nho</h2></div><Link href="/reports">Xem báo cáo →</Link></div>
        {error ? <div className="state-card" role="alert">{error}</div> : !overview ? <PageGrapeLoader /> : (
          <div className="stats-grid">
            <StatCard label="Tổng thu hoạch" value={formatKg(overview.total_harvest_kg)} tone="green" />
            <StatCard label="Đã bán" value={formatKg(overview.total_sold_kg)} />
            <StatCard label="Còn lại" value={formatKg(overview.remaining_kg)} tone="gold" />
            <StatCard label="Doanh thu bán hàng" value={formatMoney(overview.total_sales_revenue)} />
            <StatCard label="Khách còn nợ" value={formatMoney(overview.total_customer_receivables)} />
            <StatCard label="Tiền công còn phải trả" value={formatMoney(overview.total_worker_payables)} />
            <StatCard label="Chi phí" value={formatMoney(overview.total_operating_expenses)} hint="Chưa gồm tiền công và tiền mua quyền thu hoạch" />
            <StatCard label="Lợi nhuận ước tính" value={formatMoney(overview.estimated_profit)} tone="green" hint="Tính theo doanh thu bán hàng và chi phí đã ghi nhận." />
          </div>
        )}
      </section>
      <div className="home-tip"><strong>Mẹ muốn ghi thêm?</strong><span>Chỉ cần nhắn cho trợ lý như đang nói chuyện bình thường. Trước khi lưu, con sẽ hỏi mẹ xác nhận.</span></div>
    </div>
  );
}
