"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageGrapeLoader } from "@/components/ui/GrapeLoaders";
import { ApiError, apiGet } from "@/lib/api";
import { formatDate, formatKg, formatMoney } from "@/lib/format";

type Section = "gardens" | "harvests" | "customers" | "workers" | "finances";
type Row = { title: string; detail?: string; value?: string; date?: string };
type Garden = { garden_id: number; garden_name: string; owner_name: string | null; location_note: string | null };
type Variety = { variety_id: number; variety_name: string };
type Season = { season_id: number; season_name: string | null; garden_id: number; variety_id: number };
type Harvest = { harvest_id: number; season_id: number; harvest_date: string; quantity_kg: string };
type Customer = { customer_id: number; customer_name: string; phone: string | null; address_note: string | null };
type Worker = { worker_id: number; worker_name: string; phone: string | null };
type Debt = { customer_id?: number; worker_id?: number; outstanding_amount: string };
type Sale = { sale_id: number; customer_id: number; sale_date: string; quantity_kg: string; total_amount: string };
type Expense = { expense_id: number; expense_date: string; category: string; amount: string; description: string | null };

const sections: Record<Section, { title: string; intro: string; empty: string }> = {
  gardens: { title: "Vườn nho", intro: "Các vườn đang được gia đình theo dõi.", empty: "Mình chưa ghi vườn nho nào." },
  harvests: { title: "Thu hoạch", intro: "Những đợt nho đã thu hoạch.", empty: "Chưa có dữ liệu thu hoạch." },
  customers: { title: "Mối sỉ", intro: "Những người mua nho của gia đình.", empty: "Mình chưa ghi mối sỉ nào." },
  workers: { title: "Nhân công", intro: "Những người đã giúp việc trong vườn.", empty: "Mình chưa ghi nhân công nào." },
  finances: { title: "Thu chi", intro: "Các khoản bán nho và chi phí đã ghi nhận.", empty: "Chưa có khoản thu chi nào được ghi." },
};

async function loadRows(section: Section): Promise<Row[]> {
  if (section === "gardens") {
    const [gardens, seasons, varieties] = await Promise.all([
      apiGet<Garden[]>("gardens"), apiGet<Season[]>("seasons"), apiGet<Variety[]>("grape-varieties"),
    ]);
    return gardens.map((garden) => {
      const gardenSeasons = seasons.filter((season) => season.garden_id === garden.garden_id);
      const names = gardenSeasons.map((season) => varieties.find((variety) => variety.variety_id === season.variety_id)?.variety_name).filter(Boolean);
      return {
        title: garden.garden_name,
        detail: [garden.location_note, garden.owner_name && `Người chăm: ${garden.owner_name}`, `${gardenSeasons.length} vụ đã ghi`, names.length && `Giống nho: ${[...new Set(names)].join(", ")}`].filter(Boolean).join(" · "),
      };
    });
  }
  if (section === "harvests") {
    const [harvests, seasons, gardens, varieties] = await Promise.all([
      apiGet<Harvest[]>("harvests"), apiGet<Season[]>("seasons"), apiGet<Garden[]>("gardens"), apiGet<Variety[]>("grape-varieties"),
    ]);
    return harvests.sort((a, b) => b.harvest_date.localeCompare(a.harvest_date)).map((harvest) => {
      const season = seasons.find((item) => item.season_id === harvest.season_id);
      const garden = gardens.find((item) => item.garden_id === season?.garden_id);
      const variety = varieties.find((item) => item.variety_id === season?.variety_id);
      return {
        title: garden?.garden_name ?? "Vườn chưa rõ tên",
        detail: [formatDate(harvest.harvest_date), variety && `Giống ${variety.variety_name}`, season?.season_name].filter(Boolean).join(" · "),
        value: formatKg(harvest.quantity_kg),
      };
    });
  }
  if (section === "customers") {
    const [customers, debts] = await Promise.all([apiGet<Customer[]>("customers"), apiGet<Debt[]>("reports/customer-receivables")]);
    return customers.map((customer) => {
      const debt = debts.find((item) => item.customer_id === customer.customer_id);
      return { title: customer.customer_name, detail: [customer.phone, customer.address_note].filter(Boolean).join(" · "), value: Number(debt?.outstanding_amount) > 0 ? `Còn nợ ${formatMoney(debt?.outstanding_amount)}` : "Không còn nợ" };
    });
  }
  if (section === "workers") {
    const [workers, debts] = await Promise.all([apiGet<Worker[]>("workers"), apiGet<Debt[]>("reports/worker-payables")]);
    return workers.map((worker) => {
      const debt = debts.find((item) => item.worker_id === worker.worker_id);
      return { title: worker.worker_name, detail: worker.phone ?? undefined, value: Number(debt?.outstanding_amount) > 0 ? `Còn trả ${formatMoney(debt?.outstanding_amount)}` : "Đã trả đủ" };
    });
  }
  const [sales, expenses, customers] = await Promise.all([
    apiGet<Sale[]>("sales"), apiGet<Expense[]>("expenses"), apiGet<Customer[]>("customers"),
  ]);
  return [
    ...sales.map((sale) => ({ title: `Bán nho cho ${customers.find((item) => item.customer_id === sale.customer_id)?.customer_name ?? "khách"}`, detail: `${formatDate(sale.sale_date)} · ${formatKg(sale.quantity_kg)}`, value: formatMoney(sale.total_amount), date: sale.sale_date })),
    ...expenses.map((expense) => ({ title: `Chi ${expense.category}`, detail: [formatDate(expense.expense_date), expense.description].filter(Boolean).join(" · "), value: formatMoney(expense.amount), date: expense.expense_date })),
  ].sort((a, b) => b.date.localeCompare(a.date));
}

export default function ReadSection({ section }: { section: Section }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState("");
  const copy = sections[section];

  useEffect(() => {
    loadRows(section).then(setRows).catch((cause) => setError(cause instanceof ApiError ? cause.message : new ApiError().message));
  }, [section]);

  return (
    <div className="page-stack">
      <div className="page-heading"><span className="eyebrow">SỔ TAY VƯỜN NHO</span><h1>{copy.title}</h1><p>{copy.intro}</p></div>
      <div className="section-heading"><h2>Đã ghi nhận</h2><Link href="/assistant">Nhờ trợ lý ghi thêm →</Link></div>
      {error ? <div className="state-card" role="alert">{error}</div> : rows === null ? <PageGrapeLoader /> : rows.length === 0 ? <div className="state-card">{copy.empty}</div> : (
        <div className="record-list">
          {rows.map((row, index) => <article className="record-card" key={`${row.title}-${index}`}><div><h3>{row.title}</h3>{row.detail && <p>{row.detail}</p>}</div>{row.value && <strong>{row.value}</strong>}</article>)}
        </div>
      )}
    </div>
  );
}
