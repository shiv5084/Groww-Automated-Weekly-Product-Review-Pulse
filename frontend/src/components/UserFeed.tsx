"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { AlertCircle } from "lucide-react";

export type Review = {
  id: string;
  text: string;
  rating: number;
  sentiment: string;
};

export default function UserFeed({ reviews }: { reviews: Review[] }) {
  return (
    <div className="glass-card h-full flex flex-col overflow-hidden relative">
      <div className="p-4 border-b border-border/50 bg-black/20 flex items-center justify-between z-10">
        <h2 className="text-lg font-semibold flex items-center gap-2 neon-text">
          <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          Live User Voices
        </h2>
        <span className="text-xs text-muted-foreground bg-primary/10 px-2 py-1 rounded-full text-primary border border-primary/20">
          Streaming
        </span>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 space-y-4 relative">
        <AnimatePresence initial={false}>
          {reviews.slice(0, 3).map((review) => (
            <FeedItem key={review.id} review={review} />
          ))}
        </AnimatePresence>
      </div>
      
      {/* Fade out at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-[#0d1117] to-transparent pointer-events-none" />
    </div>
  );
}

function FeedItem({ review }: { review: Review }) {
  const [expanded, setExpanded] = useState(false);
  const isNegative = review.rating <= 2 || review.sentiment === "negative";

  return (
    <motion.div
      initial={{ opacity: 0, x: -20, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ type: "spring", stiffness: 300, damping: 25 }}
      className={`p-3 rounded-lg border backdrop-blur-sm cursor-pointer transition-all ${
        isNegative 
          ? "bg-destructive/5 border-destructive/30 hover:border-destructive/60 hover:bg-destructive/10" 
          : "bg-white/5 border-white/10 hover:border-primary/40 hover:bg-white/10"
      }`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex justify-between items-start gap-2 mb-1">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
            isNegative ? "bg-destructive/20 text-destructive" : "bg-primary/20 text-primary"
          }`}>
            ★ {review.rating.toFixed(1)}
          </span>
          {isNegative && <AlertCircle className="w-3 h-3 text-destructive animate-pulse" />}
        </div>
      </div>
      
      <p className={`text-sm text-foreground/90 leading-relaxed ${!expanded ? "line-clamp-2" : ""}`}>
        "{review.text}"
      </p>
    </motion.div>
  );
}
