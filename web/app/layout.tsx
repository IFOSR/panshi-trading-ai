import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "磐石 | 中国期货策略代理",
  description: "可审计的八步期货策略控制台"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
