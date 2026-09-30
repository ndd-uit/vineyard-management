"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { SignOutButton, useAuth } from "@clerk/nextjs";

const links = [
  { href: "/", label: "Trang chủ" },
  { href: "/assistant", label: "Trợ lý AI" },
  { href: "/gardens", label: "Vườn nho" },
  { href: "/harvests", label: "Thu hoạch" },
  { href: "/customers", label: "Mối sỉ" },
  { href: "/workers", label: "Nhân công" },
  { href: "/finances", label: "Thu chi" },
  { href: "/reports", label: "Báo cáo" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const { isSignedIn } = useAuth();

  if (pathname.startsWith("/sign-in")) {
    return <main className="main-content">{children}</main>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Điều hướng chính">
        <Link className="brand" href="/">
          <span className="brand-mark" aria-hidden="true"><Image src="/grape-logo.png" alt="" width={56} height={56} priority /></span>
          <span><strong>Vườn nhà</strong><small>Ghi chép mùa nho</small></span>
        </Link>
        <p className="nav-caption">DÀNH CHO MẸ</p>
        <nav className="side-links">
          {links.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={pathname === item.href ? "page" : undefined}
              className={`nav-link ${item.href === "/assistant" ? "nav-ai" : ""} ${pathname === item.href ? "active" : ""}`}
            >
              <span className="nav-dot" aria-hidden="true" />{item.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-note">Mọi khoản ghi lại đều cần mẹ xác nhận trước khi lưu.</div>
        {isSignedIn && <SignOutButton><button type="button" className="nav-link">Đăng xuất</button></SignOutButton>}
      </aside>

      <div className="main-column">
        <header className="mobile-header">
          <Link className="mobile-brand" href="/"><span className="mobile-brand-mark" aria-hidden="true"><Image src="/grape-logo.png" alt="" width={42} height={42} priority /></span>Vườn nhà</Link>
          <button type="button" className="menu-button" onClick={() => setMenuOpen(!menuOpen)} aria-expanded={menuOpen} aria-controls="mobile-menu">
            {menuOpen ? "Đóng" : "Danh mục"}
          </button>
        </header>
        {menuOpen && (
          <nav id="mobile-menu" className="mobile-menu" aria-label="Danh mục">
            {links.map((item) => (
              <Link key={item.href} href={item.href} onClick={() => setMenuOpen(false)} aria-current={pathname === item.href ? "page" : undefined}>
                {item.label}
              </Link>
            ))}
          </nav>
        )}
        <main className="main-content" id="main-content">{children}</main>
      </div>

      <nav className="bottom-nav" aria-label="Điều hướng nhanh">
        {links.filter((item) => ["/", "/assistant", "/gardens", "/reports"].includes(item.href)).map((item) => (
          <Link key={item.href} href={item.href} aria-current={pathname === item.href ? "page" : undefined}>
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
