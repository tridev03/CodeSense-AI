import { Suspense } from "react";
import { AppSidebar } from "@/components/app-sidebar";
import { Navbar } from "@/components/navbar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="min-h-screen bg-black" />}>
      <div className="flex h-screen overflow-hidden bg-black text-white">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <Navbar />
          <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
            {children}
          </main>
        </div>
      </div>
    </Suspense>
  );
}
