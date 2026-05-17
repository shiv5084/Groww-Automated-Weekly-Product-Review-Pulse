"use client";

import { useState, useEffect, useRef } from "react";
import { getLatestReport, checkHealth } from "@/lib/api";
import Ticker from "@/components/Ticker";
import Header from "@/components/Header";
import ThemeCards from "@/components/ThemeCards";
import UserFeed, { Review } from "@/components/UserFeed";
import Recommendations from "@/components/Recommendations";
import ChartsDashboard from "@/components/ChartsDashboard";

export default function Dashboard() {
  const [isOnline, setIsOnline] = useState<boolean | null>(null);
  
  // Streaming States
  const [tickerMsgs, setTickerMsgs] = useState<string[]>(["Waiting for live data stream..."]);
  const [liveThemes, setLiveThemes] = useState<any[]>([]);
  const [liveReviews, setLiveReviews] = useState<Review[]>([]);
  const [actions, setActions] = useState<string[]>([]);
  
  // Chart States
  const [trendData, setTrendData] = useState<any[]>([]);
  
  // Data source refs for simulation
  const rawReviewsRef = useRef<any[]>([]);
  const originalReviewsRef = useRef<any[]>([]);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    initStream();
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  async function initStream() {
    try {
      await checkHealth();
      setIsOnline(true);
      const data = await getLatestReport();
      
      if (data && data.themes) {
        // Parse backend data to setup initial state
        const themesArr = Object.values(data.themes).map((t: any) => ({
          theme_name: t.theme_name,
          count: 0, // Start at 0 for simulation
          target_count: t.count || 0, // Target to stop at
          avg_rating: t.avg_rating || 0,
          sentiment: t.sentiment || "neutral",
        }));
        
        setLiveThemes(themesArr);
        
        // Extract all reviews into a pool for simulation
        let allReviews: any[] = [];
        Object.values(data.themes).forEach((t: any) => {
          if (t.reviews) {
            allReviews = [...allReviews, ...t.reviews.map((r: any) => ({...r, theme: t.theme_name, sentiment: t.sentiment}))];
          }
        });
        // Shuffle pool
        allReviews.sort(() => Math.random() - 0.5);
        rawReviewsRef.current = [...allReviews];
        originalReviewsRef.current = [...allReviews];

        // Extract actions from markdown
        const actionLines = data.pulse_md.match(/## Recommended Actions\n\n([\s\S]*?)$/)?.[1] || "";
        const extractedActions = actionLines.split("\n").filter((l: string) => l.trim().match(/^\d+\./)).map((l: string) => l.replace(/^\d+\.\s*/, ""));
        setActions(extractedActions.length > 0 ? extractedActions : [
          "Fix sudden logout issue during onboarding.",
          "Enhance login error messaging for clarity.",
          "Implement auto-login retry feature."
        ]);

        // Start Simulation
        startSimulation();
      }
    } catch (err) {
      console.error(err);
      setIsOnline(false);
    }
  }

  function startSimulation() {
    let tickCount = 0;
    
    intervalRef.current = setInterval(() => {
      tickCount++;
      const now = new Date().toLocaleTimeString('en-US', { hour12: false, hour: "numeric", minute: "numeric", second: "numeric" });
      
      // 1. Pop a review from the pool
      let pool = rawReviewsRef.current;
      if (pool.length === 0 && originalReviewsRef.current.length > 0) {
        pool = [...originalReviewsRef.current].sort(() => Math.random() - 0.5);
        rawReviewsRef.current = pool;
      }

      if (pool.length > 0) {
        // Pick random 1-2 reviews
        const batchSize = Math.random() > 0.7 ? 2 : 1;
        const newReviews: Review[] = [];
        
        for(let i=0; i<batchSize && pool.length>0; i++) {
           const r = pool.pop();
           newReviews.push({
             id: Math.random().toString(36).substr(2, 9),
             text: r.text,
             rating: r.rating,
             sentiment: r.sentiment
           });
        }
        
        setLiveReviews(prev => [...newReviews, ...prev].slice(0, 30)); // Keep last 30
        
        // 2. Update Ticker
        const msgs = newReviews.map(r => `New ${r.sentiment} review received (${r.rating}/5 stars)`);
        setTickerMsgs(prev => [...msgs, ...prev].slice(0, 5));

        // 3. Update Theme counts
        setLiveThemes(prev => prev.map(t => {
          if (t.count >= t.target_count) return t;
          const remaining = t.target_count - t.count;
          // Randomly increment but quickly approach target
          const boost = Math.max(1, Math.floor(Math.random() * (remaining * 0.4)));
          return { ...t, count: Math.min(t.count + boost, t.target_count) };
        }));
      } else {
        setTickerMsgs(["Stream stabilized. Processing backlog..."]);
      }

      // 4. Update Trend Chart
      setTrendData(prev => {
        const newData = [...prev];
        if (newData.length > 20) newData.shift();
        
        // Generate fluctuating sentiment streams
        const basePos = 10 + Math.random() * 20 + (tickCount % 10);
        const baseNeg = 5 + Math.random() * 15;
        
        newData.push({
          time: now,
          positive: Math.floor(basePos),
          negative: Math.floor(baseNeg),
          neutral: Math.floor(10 + Math.random() * 5),
          volume: Math.floor(basePos + baseNeg + 10)
        });
        return newData;
      });

    }, 2500); // Tick every 2.5s
  }

  // Derive theme chart data
  const themeChartData = liveThemes.map(t => ({
    name: t.theme_name,
    volume: t.count
  })).sort((a,b) => b.volume - a.volume).slice(0, 5);

  return (
    <main className="min-h-screen flex flex-col bg-[#0d1117] text-[#e6edf3] font-sans selection:bg-primary/30 relative overflow-hidden">
      {/* Background Orbs */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-primary/10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[30%] h-[30%] rounded-full bg-[#1f6feb]/10 blur-[100px] pointer-events-none" />
      
      {/* Header */}
      <Header isOnline={isOnline} />
        
      {/* Ticker Component */}
      <Ticker messages={tickerMsgs} />

      {/* Main Content Dashboard */}
      <div className="flex-1 max-w-7xl mx-auto w-full p-4 md:p-6 flex flex-col gap-6 z-10">
        
        {/* Top Row: Theme Cards Grid */}
        <section>
          <ThemeCards themes={liveThemes.slice(0, 3)} />
        </section>

        {/* Middle Row: User Feed & Recommendations */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[800px] lg:h-[400px]">
          <div className="lg:col-span-2 h-full">
            <UserFeed reviews={liveReviews} />
          </div>
          <div className="h-full">
            <Recommendations actions={actions} />
          </div>
        </section>

        {/* Bottom Row: Charts */}
        <section className="h-[1050px] lg:h-[350px]">
          <ChartsDashboard trendData={trendData} themeData={themeChartData} />
        </section>

      </div>
    </main>
  );
}
