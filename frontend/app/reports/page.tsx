"use client";

import { useEffect, useState } from "react";
import StatCard from "@/components/dashboard/StatCard";
import { PageGrapeLoader } from "@/components/ui/GrapeLoaders";
import { ApiError, apiGet } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { Overview } from "@/types/api";

type CustomerDebt = { customer_name: string; outstanding_amount: string };
type WorkerDebt = { worker_name: string; outstanding_amount: string };

export default function ReportsPage() {
  const [data, setData] = useState<{ overview: Overview; customers: CustomerDebt[]; workers: WorkerDebt[] } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiGet<Overview>("reports/overview"),
      apiGet<CustomerDebt[]>("reports/customer-receivables"),
      apiGet<WorkerDebt[]>("reports/worker-payables"),
    ]).then(([overview, customers, workers]) => setData({ overview, customers, workers })).catch((cause) => setError(cause instanceof ApiError ? cause.message : new ApiError().message));
  }, []);

  return (
    <div className="page-stack">
      <div className="page-heading"><span className="eyebrow">NHÌN LẠI MÙA NHO</span><h1>Báo cáo</h1><p>Các con số dưới đây được tính từ những khoản đã ghi.</p></div>
      {error ? <div className="state-card" role="alert">{error}</div> : !data ? <PageGrapeLoader message="Con đang lấy báo cáo cho mẹ..." /> : (
        <>
          <div className="stats-grid">
            <StatCard label="Doanh thu bán hàng" value={formatMoney(data.overview.total_sales_revenue)} />
            <StatCard label="Khách còn nợ" value={formatMoney(data.overview.total_customer_receivables)} tone="gold" />
            <StatCard label="Tiền công còn phải trả" value={formatMoney(data.overview.total_worker_payables)} />
            <StatCard label="Lợi nhuận ước tính" value={formatMoney(data.overview.estimated_profit)} tone="green" hint="Tính theo doanh thu bán hàng và chi phí đã ghi nhận." />
          </div>
          <div className="report-columns">
            <section className="report-list"><h2>Khách còn nợ</h2>{data.customers.filter((item) => Number(item.outstanding_amount) > 0).length === 0 ? <p>Hiện chưa có công nợ khách hàng.</p> : data.customers.filter((item) => Number(item.outstanding_amount) > 0).map((item, index) => <div className="report-row" key={`${item.customer_name}-${index}`}><span>{item.customer_name}</span><strong>{formatMoney(item.outstanding_amount)}</strong></div>)}</section>
            <section className="report-list"><h2>Tiền công còn trả</h2>{data.workers.filter((item) => Number(item.outstanding_amount) > 0).length === 0 ? <p>Hiện không còn tiền công phải trả.</p> : data.workers.filter((item) => Number(item.outstanding_amount) > 0).map((item, index) => <div className="report-row" key={`${item.worker_name}-${index}`}><span>{item.worker_name}</span><strong>{formatMoney(item.outstanding_amount)}</strong></div>)}</section>
          </div>
        </>
      )}
    </div>
  );
}
