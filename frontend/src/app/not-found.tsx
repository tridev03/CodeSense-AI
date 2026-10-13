"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

export default function NotFound() {
  const router = useRouter();
  return (
    <div className="min-h-screen bg-black flex flex-col items-center justify-center px-6 text-center">
      {/* Ambient glow */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 40% at 50% 70%, rgba(107,66,29,0.18) 0%, transparent 70%)",
        }}
      />

      {/* 404 */}
      <span className="text-[10rem] font-extralight leading-none text-[#D99A45] opacity-20 select-none">
        404
      </span>

      <h1 className="mt-[-2rem] text-3xl font-light text-[#F5F5F5] tracking-tight">
        Page not found
      </h1>
      <p className="mt-3 text-[#71717A] text-sm max-w-xs">
        The page you&apos;re looking for doesn&apos;t exist or has been moved.
      </p>

      <div className="mt-8 flex gap-3">
        <button
          onClick={() => router.back()}
          className="px-5 py-2.5 rounded-full border border-[#303030] text-[#A1A1AA] text-sm hover:border-[#D99A45] hover:text-[#D99A45] transition-colors"
        >
          Go back
        </button>
        <Link
          href="/"
          className="px-5 py-2.5 rounded-full bg-[#D99A45] text-black text-sm font-medium hover:brightness-110 transition-all"
        >
          Home
        </Link>
      </div>
    </div>
  );
}

