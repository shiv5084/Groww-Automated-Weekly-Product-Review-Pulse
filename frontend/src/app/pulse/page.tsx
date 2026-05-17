"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { getLatestReport, checkHealth } from "@/lib/api";
import Header from "@/components/Header";
import { ExternalLink } from "lucide-react";

export default function PulseNotePage() {
  const [isOnline, setIsOnline] = useState<boolean | null>(null);
  const [pulseMd, setPulseMd] = useState<string>("");

  useEffect(() => {
    async function load() {
      try {
        await checkHealth();
        setIsOnline(true);
        const data = await getLatestReport();
        if (data && data.pulse_md) {
          setPulseMd(data.pulse_md);
        }
      } catch (err) {
        console.error(err);
        setIsOnline(false);
      }
    }
    load();
  }, []);

  return (
    <main className="min-h-screen flex flex-col bg-[#0d1117] text-[#e6edf3] font-sans relative overflow-hidden">
      {/* Background Orbs */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-primary/10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[30%] h-[30%] rounded-full bg-[#1f6feb]/10 blur-[100px] pointer-events-none" />
      
      {/* Shared Header */}
      <Header isOnline={isOnline} />

      <div className="flex-1 max-w-4xl mx-auto w-full p-4 md:p-8 z-10 flex flex-col gap-8">
        <div className="glass-card p-8 md:p-12 relative overflow-hidden">
          {/* Subtle decoration inside the card */}
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-bl-full blur-2xl pointer-events-none" />
          
          <div className="prose prose-invert prose-primary max-w-none">
            {pulseMd ? (
              <ReactMarkdown
                components={{
                  h1: ({node, ...props}) => <h1 className="text-3xl font-bold text-white mb-6 pb-4 border-b border-white/10" {...props} />,
                  h2: ({node, ...props}) => <h2 className="text-2xl font-semibold text-primary mt-10 mb-4 flex items-center gap-2 neon-text" {...props} />,
                  p: ({node, ...props}) => <p className="text-foreground/90 leading-relaxed mb-4 text-lg" {...props} />,
                  blockquote: ({node, ...props}) => (
                    <blockquote className="border-l-4 border-primary pl-6 italic text-foreground bg-primary/5 py-4 my-6 rounded-r-xl shadow-inner" {...props} />
                  ),
                  li: ({node, ...props}) => <li className="text-foreground/90 ml-4 mb-2 text-lg" {...props} />,
                  ul: ({node, ...props}) => <ul className="list-disc mb-6" {...props} />,
                  ol: ({node, ...props}) => <ol className="list-decimal mb-6" {...props} />,
                  strong: ({node, ...props}) => <strong className="text-white font-semibold" {...props} />
                }}
              >
                {pulseMd}
              </ReactMarkdown>
            ) : (
              <div className="flex justify-center items-center h-48">
                <p className="text-muted-foreground animate-pulse text-lg">Loading Pulse Note...</p>
              </div>
            )}
          </div>
        </div>

        {/* Footer with Google Docs Link */}
        <footer className="glass-card p-6 flex flex-col sm:flex-row items-center justify-between gap-4 mt-auto">
          <div>
            <h3 className="text-sm font-semibold text-white">Master Document</h3>
            <p className="text-xs text-muted-foreground mt-1">This pulse note is published and synced automatically.</p>
          </div>
          <a 
            href="https://docs.google.com/document/d/1GnP6rppyomekIjv4c9HJM8yDFndb75AFgqcf5FXgFK0/edit"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 glass-button px-5 py-2.5 rounded-full text-sm font-medium text-primary border border-primary/30 hover:border-primary hover:bg-primary/10 transition-colors"
          >
            <ExternalLink className="w-4 h-4" />
            Open in Google Docs
          </a>
        </footer>
      </div>
    </main>
  );
}
