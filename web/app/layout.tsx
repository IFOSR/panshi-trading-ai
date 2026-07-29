import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "磐石交易AI",
  description: "面向中国期货市场的可审计多模态交易分析"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
