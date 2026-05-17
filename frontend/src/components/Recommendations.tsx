"use client";

import { motion } from "framer-motion";
import { Sparkles, ChevronRight } from "lucide-react";

export default function Recommendations({ actions }: { actions: string[] }) {
  return (
    <div className="glass-card h-full flex flex-col overflow-hidden relative">
      <div className="p-4 border-b border-border/50 bg-black/20 flex items-center justify-between z-10">
        <h2 className="text-lg font-semibold flex items-center gap-2 neon-text">
          <Sparkles className="w-5 h-5 text-primary" />
          AI Recommendations
        </h2>
      </div>
      
      <div className="flex-1 p-4 space-y-4 overflow-y-auto z-10">
        {actions.length === 0 && (
          <p className="text-sm text-muted-foreground text-center mt-10">Waiting for insights...</p>
        )}
        
        {actions.map((action, idx) => (
          <motion.div
            key={idx}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: idx * 0.2, type: "spring" }}
            className="group relative p-[1px] rounded-xl overflow-hidden cursor-pointer"
          >
            {/* Animated Pulse Border for top priority */}
            {idx === 0 && (
              <div className="absolute inset-0 bg-gradient-to-r from-primary via-transparent to-primary opacity-50 animate-[spin_4s_linear_infinite]" />
            )}
            
            <div className={`relative bg-[#161b22]/90 backdrop-blur-xl h-full w-full rounded-xl p-4 border flex items-start gap-3 transition-colors ${
              idx === 0 ? "border-transparent" : "border-white/10 hover:border-primary/50"
            }`}>
              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                idx === 0 ? "bg-primary text-black neon-border" : "bg-white/10 text-white"
              }`}>
                {idx + 1}
              </div>
              <p className="text-sm text-foreground/90 flex-1 leading-snug">
                {action}
              </p>
              <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors opacity-0 group-hover:opacity-100" />
            </div>
          </motion.div>
        ))}
      </div>
      
      {/* Background decoration */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-primary/5 blur-3xl rounded-full pointer-events-none" />
    </div>
  );
}
