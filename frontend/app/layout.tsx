import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SegmentIQ — Intelligent Video Segmentation",
  description: "AI-powered video segmentation using TwelveLabs Marengo + Pegasus via AWS Bedrock",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-200">
        <nav className="border-b border-slate-800 px-6 py-3 flex items-center gap-3">
          <span className="text-teal-500 font-bold text-lg tracking-tight">SegmentIQ</span>
          <span className="text-slate-600 text-xs">|</span>
          <span className="text-slate-500 text-xs">Intelligent Video Segmentation · TwelveLabs + AWS Bedrock</span>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
