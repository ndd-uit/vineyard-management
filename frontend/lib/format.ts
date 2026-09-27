const numberFormatter = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });

export function formatNumber(value: number | string | null | undefined): string {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? numberFormatter.format(parsed) : "0";
}

export function formatMoney(value: number | string | null | undefined): string {
  return `${formatNumber(value)}đ`;
}

export function formatKg(value: number | string | null | undefined): string {
  return `${formatNumber(value)} kg`;
}

export function formatDate(value: string): string {
  const [year, month, day] = value.slice(0, 10).split("-");
  return year && month && day ? `${day}/${month}/${year}` : value;
}
