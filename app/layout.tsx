import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "招投标情报工作台",
  description: "基于项目事件、证据检索与时序记忆的本地招投标情报系统。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
