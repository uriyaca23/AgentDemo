import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "LLM Agent Hub | Offline Ready",
  description: "Enterprise-grade local and OpenRouter LLM interface",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans h-screen w-screen overflow-hidden flex bg-background text-foreground`}>
        {children}
      </body>
    </html>
  );
}
