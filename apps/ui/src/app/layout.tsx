import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Nav from "@/components/Nav";
import ServerConfig from "@/components/ServerConfig";
import { SettingsProvider } from "@/lib/store";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "fakzed 控制台",
  description: "Fakzed agent platform console",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="zh-CN"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-zinc-950 text-zinc-100">
        <SettingsProvider>
          <div className="flex h-screen flex-col">
            <ServerConfig />
            <div className="flex min-h-0 flex-1">
              <Nav />
              <main className="min-w-0 flex-1 overflow-y-auto p-4">{children}</main>
            </div>
          </div>
        </SettingsProvider>
      </body>
    </html>
  );
}
