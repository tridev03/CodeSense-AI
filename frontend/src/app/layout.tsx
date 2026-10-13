import { Suspense } from "react";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "CodeSense AI",
  description: "AI Knowledge Agent for your codebase",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-black text-white selection:bg-amber/30 selection:text-amber-300 min-h-screen flex flex-col`}
      >
        <AuthProvider>
          <TooltipProvider>
            <Suspense fallback={null}>
              {children}
            </Suspense>
            <Toaster 
              theme="dark" 
              toastOptions={{ 
                className: 'bg-surface-2 border-border text-white' 
              }} 
            />
          </TooltipProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
