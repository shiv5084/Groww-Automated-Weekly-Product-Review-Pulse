"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";

export default function Ticker({ messages }: { messages: string[] }) {
  const [currentIdx, setCurrentIdx] = useState(0);

  useEffect(() => {
    if (!messages || messages.length === 0) return;
    const interval = setInterval(() => {
      setCurrentIdx((prev) => (prev + 1) % messages.length);
    }, 4000);
    return () => clearInterval(interval);
  }, [messages]);

  if (!messages || messages.length === 0) return null;

  return (
    <div className="w-full bg-black/50 border-y border-primary/20 h-10 flex items-center overflow-hidden relative">
      <div className="absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-[#0d1117] to-transparent z-10" />
      <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-[#0d1117] to-transparent z-10" />
      
      <motion.div
        key={currentIdx}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className="w-full text-center text-sm font-medium text-primary neon-text tracking-wide whitespace-nowrap px-8"
      >
        <span className="mr-2 opacity-70">⚡ LIVE UPDATE:</span>
        {messages[currentIdx]}
      </motion.div>
    </div>
  );
}
