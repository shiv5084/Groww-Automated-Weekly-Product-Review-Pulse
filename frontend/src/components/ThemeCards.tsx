"use client";

import { motion } from "framer-motion";
import { LineChart, Line, ResponsiveContainer } from "recharts";

type Theme = {
  theme_name: string;
  count: number;
  avg_rating: number;
  sentiment: string;
};

// Map sentiment to colors and emojis
const SENTIMENT_MAP: Record<string, { color: string; emoji: string }> = {
  positive: { color: "#00d09c", emoji: "🙂" },
  neutral: { color: "#f57c00", emoji: "😐" },
  negative: { color: "#f85149", emoji: "😟" },
};

export default function ThemeCards({ themes }: { themes: Theme[] }) {
  if (!themes || themes.length === 0) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 relative perspective-1000">
      {themes.map((theme, idx) => {
        const meta = SENTIMENT_MAP[theme.sentiment] || SENTIMENT_MAP.neutral;
        // Generate a fake sparkline based on the rating
        const data = Array.from({ length: 10 }).map((_, i) => ({
          value: theme.avg_rating + Math.sin(i + idx) * 0.5,
        }));

        return (
          <motion.div
            key={theme.theme_name}
            initial={{ opacity: 0, y: 50, rotateX: 20 }}
            animate={{ opacity: 1, y: 0, rotateX: 0 }}
            transition={{ duration: 0.6, delay: idx * 0.1, type: "spring" }}
            className="glass-card p-6 flex flex-col justify-between group h-40 relative overflow-hidden"
            style={{
              boxShadow: `0 10px 30px -10px ${meta.color}40, inset 0 1px 0 0 rgba(255, 255, 255, 0.1)`,
            }}
          >
            {/* Background Glow */}
            <div 
              className="absolute -top-10 -right-10 w-24 h-24 rounded-full blur-2xl opacity-20 transition-opacity group-hover:opacity-40"
              style={{ backgroundColor: meta.color }}
            />
            
            <div className="flex justify-between items-start z-10">
              <h3 className="text-xl font-bold tracking-tight" style={{ color: meta.color, textShadow: `0 0 10px ${meta.color}80` }}>
                {theme.theme_name}
              </h3>
              <span className="text-2xl">{meta.emoji}</span>
            </div>
            
            <div className="z-10 mt-auto">
              <div className="flex items-end justify-between">
                <div>
                  <p className="text-2xl font-bold text-white">{theme.count} <span className="text-sm font-normal text-muted-foreground">reviews</span></p>
                  <p className="text-sm text-muted-foreground">avg {theme.avg_rating.toFixed(2)}/5</p>
                </div>
                
                {/* Mini Sparkline */}
                <div className="w-20 h-10 opacity-70 group-hover:opacity-100 transition-opacity">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data}>
                      <Line 
                        type="monotone" 
                        dataKey="value" 
                        stroke={meta.color} 
                        strokeWidth={2} 
                        dot={false}
                        isAnimationActive={true}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
