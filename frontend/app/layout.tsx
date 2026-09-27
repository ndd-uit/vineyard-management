import type { Metadata } from "next";
import AppShell from "@/components/layout/AppShell";
import "@fontsource/be-vietnam-pro/400.css";
import "@fontsource/be-vietnam-pro/500.css";
import "@fontsource/be-vietnam-pro/600.css";
import "@fontsource/be-vietnam-pro/700.css";
import "@fontsource/be-vietnam-pro/800.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vườn nhà | Sổ tay vườn nho",
  description: "Theo dõi mùa nho và trò chuyện với trợ lý của gia đình.",
  icons: {
    icon: [{ url: "/grape-logo.png", type: "image/png" }],
    shortcut: "/grape-logo.png",
    apple: "/grape-logo.png",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi">
      <body><AppShell>{children}</AppShell></body>
    </html>
  );
}
