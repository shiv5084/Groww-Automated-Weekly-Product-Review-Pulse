"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { PlayCircle, Loader2 } from "lucide-react";
import { motion } from "framer-motion";

const PIPELINE_STAGES = [
  "Scraping App Stores...",
  "Scrubbing PII...",
  "LLM Theme Clustering...",
  "Generating Pulse...",
  "Agentic Quality Check...",
  "Publishing via MCP..."
];

export default function Header({ isOnline }: { isOnline?: boolean | null }) {
  const pathname = usePathname();
  const [isGenerating, setIsGenerating] = useState(false);
  const [stageIndex, setStageIndex] = useState(-1);

  const STAGE_DURATIONS = [20000, 10000, 35000, 30000, 20000, 10000]; // Total ~2 mins

  const handleGenerate = async () => {
    if (isGenerating) return;
    setIsGenerating(true);
    setStageIndex(0);
    try {
      // 1. Get initial timestamp to detect when it's done
      let initialTimestamp = 0;
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:10001";
      try {
        const initRes = await fetch(`${backendUrl}/latest-report`, { cache: "no-store" });
        if (initRes.ok) {
          const initData = await initRes.json();
          initialTimestamp = initData.last_updated || 0;
        }
      } catch (e) {
         console.warn("Could not get initial timestamp");
      }

      // 2. Trigger pipeline
      const res = await fetch(`${backendUrl}/run?weeks=12&scrape=True&dry_run=False`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to trigger pipeline");
      
      // 3. Advance stages with realistic timings
      let currentStage = 0;
      
      const startPolling = (oldTimestamp: number) => {
        const pollInterval = setInterval(async () => {
           try {
             const pollRes = await fetch(`${backendUrl}/latest-report`, { cache: "no-store" });
             if (pollRes.ok) {
               const pollData = await pollRes.json();
               if (pollData.last_updated && pollData.last_updated > oldTimestamp) {
                 clearInterval(pollInterval);
                 setIsGenerating(false);
                 setStageIndex(-1);
                 window.location.reload(); // Refresh to see latest data
               }
             }
           } catch(e) {
             console.error("Polling error", e);
           }
        }, 5000);
      };

      const advanceStage = () => {
        if (currentStage < PIPELINE_STAGES.length - 1) {
          currentStage++;
          setStageIndex(currentStage);
          
          if (currentStage < PIPELINE_STAGES.length - 1) {
             setTimeout(advanceStage, STAGE_DURATIONS[currentStage]);
          } else {
             // Reached last stage, wait for actual backend completion
             startPolling(initialTimestamp);
          }
        }
      };
      
      setTimeout(advanceStage, STAGE_DURATIONS[0]);
      
    } catch (err) {
      console.error(err);
      alert("Error triggering pipeline. Ensure backend is running.");
      setIsGenerating(false);
      setStageIndex(-1);
    }
  };

  return (
    <header className="sticky top-0 z-50 bg-[#0d1117]/80 backdrop-blur-xl border-b border-white/10">
      <div className="max-w-7xl mx-auto px-4 md:px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-6">
          {/* Logo & Title */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 flex items-center justify-center rounded-full shadow-[0_0_10px_rgba(0,208,156,0.3)]">
              <img src="/groww_logo.png" alt="Groww Logo" className="w-full h-full object-contain" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-white leading-tight">
                Groww Pulse
              </h1>
            </div>
          </div>
          
          {/* Navigation Tabs */}
          <nav className="hidden md:flex items-center gap-2 border-l border-white/10 pl-6 h-8">
            <Link 
              href="/" 
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                pathname === "/" 
                  ? "bg-primary/20 text-primary border border-primary/30 neon-text" 
                  : "text-muted-foreground hover:text-white hover:bg-white/5"
              }`}
            >
              Live Dashboard
            </Link>
            <Link 
              href="/pulse" 
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                pathname === "/pulse" 
                  ? "bg-primary/20 text-primary border border-primary/30 neon-text" 
                  : "text-muted-foreground hover:text-white hover:bg-white/5"
              }`}
            >
              Pulse Note
            </Link>
          </nav>
        </div>
        
        {/* Actions & Status */}
        <div className="flex items-center gap-4">
          <button
            onClick={handleGenerate}
            disabled={isGenerating}
            className="hidden sm:flex items-center gap-2 glass-button rounded-full text-sm font-medium text-white border border-white/20 hover:border-primary/50 relative overflow-hidden transition-all duration-300"
            style={{ width: isGenerating ? '240px' : 'auto', padding: isGenerating ? '6px 16px' : '6px 16px', justifyContent: 'center' }}
          >
            {isGenerating && (
              <motion.div 
                className="absolute left-0 top-0 bottom-0 bg-primary/40 z-0"
                initial={{ width: "0%" }}
                animate={{ width: stageIndex === PIPELINE_STAGES.length - 1 ? "95%" : `${((stageIndex + 1) / PIPELINE_STAGES.length) * 100}%` }}
                transition={{ 
                  duration: stageIndex >= 0 && stageIndex < STAGE_DURATIONS.length ? STAGE_DURATIONS[stageIndex] / 1000 : 2, 
                  ease: "linear" 
                }}
              />
            )}
            
            <div className="z-10 flex items-center gap-2 whitespace-nowrap">
              {isGenerating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin text-primary" />
                  <span className="text-xs">{PIPELINE_STAGES[stageIndex]}</span>
                </>
              ) : (
                <>
                  <PlayCircle className="w-4 h-4 text-primary" />
                  <span>Generate Pulse</span>
                </>
              )}
            </div>
          </button>
          
          {isOnline !== undefined && (
            <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${
              isOnline ? "bg-primary/10 border-primary/30 text-primary neon-text" : "bg-destructive/10 border-destructive/30 text-destructive"
            }`}>
              <div className={`w-2 h-2 rounded-full ${isOnline ? "bg-primary animate-pulse" : "bg-destructive"}`} />
              <span className="hidden sm:inline">{isOnline ? "SYSTEM ONLINE" : "OFFLINE"}</span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
