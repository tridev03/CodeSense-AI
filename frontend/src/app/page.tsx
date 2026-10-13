"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/navbar";
import { BlackHoleHeroSection } from "@/components/ui/blackhole-hero-section";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Atom, Compass, ArrowRight, Shield, Layers, Binary } from "lucide-react";

/** True while the viewport is narrow. Drives the layout swap below. */
function useNarrow(query = "(max-width: 767px)") {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const m = window.matchMedia(query);
    const sync = () => setNarrow(m.matches);
    sync();
    m.addEventListener("change", sync);
    return () => m.removeEventListener("change", sync);
  }, [query]);
  return narrow;
}

export default function BlackHoleHeroSectionDemo() {
  const narrow = useNarrow();
  const [showMaths, setShowMaths] = useState(false);

  return (
    <div className="min-h-screen bg-black flex flex-col">
      {/* Top Navbar */}
      <Navbar />

      {/* Main Hero Section */}
      <section className="relative flex-1 min-h-[92svh] w-full bg-black md:min-h-[720px]">
        <BlackHoleHeroSection
          focus={narrow ? [0.5, 0.74] : [0.73, 0.42]}
          scrim={narrow ? "top" : "none"}
          scrimStrength={narrow ? 0.9 : 0}
          distance={24}
          elevation={narrow ? -7 : -5.5}
          roll={-20}
          fov={narrow ? 58 : 42}
          diskInner={3}
          diskOuter={15}
          diskThickness={0.26}
          diskDensity={1}
          brightness={1}
          spinSpeed={0.06}
          grain={0.48}
          doppler={0.35}
          hotColor="#FFF3DE"
          midColor="#FF9838"
          coolColor="#8E3A0B"
          starBrightness={0}
          glow={1}
          exposure={0.9}
          vignette={0.28}
          steps={narrow ? 200 : 320}
          resolution={narrow ? 0.65 : 0.75}
        >
          <div className="flex h-full min-h-[92svh] items-start px-6 pt-14 sm:px-10 md:min-h-[720px] md:items-center md:pt-0 lg:px-24">
            <div className="max-w-[34rem]">
              <h1 className="text-[2.6rem] font-light leading-[1.08] tracking-[-0.035em] text-white sm:text-6xl lg:text-[4.25rem]">
                Light does not
                <br />
                leave here
              </h1>

              <p className="mt-6 max-w-[30rem] text-[0.95rem] leading-[1.65] text-white/65 md:mt-7">
                The ring above the shadow is the far side of the disc, bent over
                the top.
                <br className="hidden sm:inline" /> Nothing put it there but gravity.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-3.5 md:mt-9">
                <Link
                  href="/app/repositories"
                  className="rounded-full bg-white px-7 py-3 text-sm font-medium text-black transition-all hover:bg-white/90 active:scale-[0.98] inline-flex items-center gap-2 shadow-lg shadow-white/5"
                >
                  Get started
                  <ArrowRight className="w-4 h-4" />
                </Link>
                <button
                  type="button"
                  onClick={() => setShowMaths(true)}
                  className="rounded-full border border-white/20 bg-transparent px-7 py-3 text-sm font-normal text-white/85 transition-all hover:border-white/40 hover:text-white active:scale-[0.98]"
                >
                  Read the maths
                </button>
              </div>
            </div>
          </div>
        </BlackHoleHeroSection>
      </section>

      {/* "Read the maths" Modal */}
      <Dialog open={showMaths} onOpenChange={setShowMaths}>
        <DialogContent className="bg-[#0D0D0D] border border-[#242424] text-[#F5F5F5] sm:max-w-xl rounded-2xl p-6 max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <div className="w-10 h-10 rounded-xl bg-[#141414] border border-[#303030] flex items-center justify-center text-[#D99A45] mb-2">
              <Atom className="w-5 h-5" />
            </div>
            <DialogTitle className="text-xl font-light tracking-tight">
              General Relativity & Shader Physics
            </DialogTitle>
            <DialogDescription className="text-xs text-[#71717A]">
              How the ray-marching shader simulates curved spacetime and accretion dynamics.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 text-xs text-[#A1A1AA] leading-relaxed mt-2">
            <div className="p-3.5 bg-[#141414] border border-[#242424] rounded-xl space-y-1.5">
              <div className="flex items-center gap-2 text-white font-medium">
                <Compass className="w-4 h-4 text-[#D99A45]" />
                <span>1. Schwarzschild Geodesic Acceleration</span>
              </div>
              <p className="font-mono text-[#D99A45] text-[11px] py-1">
                a = -1.5 · RS / r³ · (pos - (pos · vel) · vel)
              </p>
              <p className="text-[11px] text-[#71717A]">
                Photons travel along null geodesics in curved 4D spacetime. The Schwarzschild acceleration deflects light backwards towards the singularity, forming the photon sphere at r = 1.5 and the apparent shadow radius at r ≈ 2.6.
              </p>
            </div>

            <div className="p-3.5 bg-[#141414] border border-[#242424] rounded-xl space-y-1.5">
              <div className="flex items-center gap-2 text-white font-medium">
                <Layers className="w-4 h-4 text-[#D99A45]" />
                <span>2. Shakura-Sunyaev Thin Disc Metric</span>
              </div>
              <p className="font-mono text-[#D99A45] text-[11px] py-1">
                T(r) ∝ (r - r_isco + 1.0)^(-0.75)
              </p>
              <p className="text-[11px] text-[#71717A]">
                Gas particles follow Keplerian circular orbits outside the Innermost Stable Circular Orbit (ISCO = 3.0 r_s). Friction and viscosity heat inner gas to white-hot temperatures while outer gas cools into deep burnt copper.
              </p>
            </div>

            <div className="p-3.5 bg-[#141414] border border-[#242424] rounded-xl space-y-1.5">
              <div className="flex items-center gap-2 text-white font-medium">
                <Binary className="w-4 h-4 text-[#D99A45]" />
                <span>3. Relativistic Doppler Beaming</span>
              </div>
              <p className="font-mono text-[#D99A45] text-[11px] py-1">
                Doppler = 1.0 + β · cos(φ + t · Ω)
              </p>
              <p className="text-[11px] text-[#71717A]">
                Because the plasma orbits at a significant fraction of light speed (v ≈ 0.4c), radiation emitted towards the observer is blue-shifted and magnified, while receding plasma is dimmed and red-shifted.
              </p>
            </div>

            <div className="pt-2 flex justify-end">
              <Link
                href="/app/repositories"
                className="bg-[#D99A45] hover:bg-[#D99A45]/90 text-black font-medium px-4 py-2 rounded-xl text-xs inline-flex items-center gap-1.5 transition-all"
                onClick={() => setShowMaths(false)}
              >
                Go to Repositories
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
