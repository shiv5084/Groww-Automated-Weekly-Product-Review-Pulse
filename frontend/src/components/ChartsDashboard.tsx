"use client";

import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

type ChartDataPoint = {
  time: string;
  positive: number;
  negative: number;
  neutral: number;
  volume: number;
};

type ThemeVolume = {
  name: string;
  volume: number;
};

const COLORS = ['#00d09c', '#f57c00', '#f85149'];

export default function ChartsDashboard({
  trendData,
  themeData,
}: {
  trendData: ChartDataPoint[];
  themeData: ThemeVolume[];
}) {
  const top3Themes = themeData.slice(0, 3);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full pb-10">
      {/* Sentiment Trend Chart */}
      <div className="glass-card p-4 flex flex-col h-72 lg:h-full lg:col-span-1">
        <h2 className="text-lg font-semibold mb-4 text-foreground/90 neon-text">
          Live Sentiment Stream
        </h2>
        <div className="flex-1 min-h-[200px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trendData} margin={{ top: 5, right: 20, bottom: 5, left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
              <XAxis dataKey="time" stroke="rgba(255,255,255,0.5)" fontSize={12} tickLine={false} axisLine={false} />
              <YAxis stroke="rgba(255,255,255,0.5)" fontSize={12} tickLine={false} axisLine={false} />
              <Tooltip 
                contentStyle={{ backgroundColor: 'rgba(13,17,23,0.9)', borderColor: 'rgba(0,208,156,0.3)', borderRadius: '8px' }}
                itemStyle={{ fontSize: '12px' }}
              />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              <Line type="monotone" dataKey="positive" stroke="#00d09c" strokeWidth={3} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="negative" stroke="#f85149" strokeWidth={3} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="neutral" stroke="#f57c00" strokeWidth={3} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Theme Comparison Bar Chart */}
      <div className="glass-card p-4 flex flex-col h-72 lg:h-full lg:col-span-1">
        <h2 className="text-lg font-semibold mb-4 text-foreground/90 neon-text">
          Active Theme Volume
        </h2>
        <div className="flex-1 min-h-[200px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={themeData} margin={{ top: 5, right: 20, bottom: 5, left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
              <XAxis dataKey="name" stroke="rgba(255,255,255,0.5)" fontSize={12} tickLine={false} axisLine={false} />
              <YAxis stroke="rgba(255,255,255,0.5)" fontSize={12} tickLine={false} axisLine={false} />
              <Tooltip 
                cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                contentStyle={{ backgroundColor: 'rgba(13,17,23,0.9)', borderColor: 'rgba(0,208,156,0.3)', borderRadius: '8px' }}
              />
              <Bar dataKey="volume" fill="#00d09c" radius={[4, 4, 0, 0]} isAnimationActive={true} animationDuration={1000} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Theme Distribution Pie Chart */}
      <div className="glass-card p-4 flex flex-col h-72 lg:h-full lg:col-span-1">
        <h2 className="text-lg font-semibold mb-4 text-foreground/90 neon-text">
          Top 3 Theme Distribution
        </h2>
        <div className="flex-1 min-h-[200px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={top3Themes}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={80}
                paddingAngle={5}
                dataKey="volume"
                stroke="rgba(0,0,0,0)"
                isAnimationActive={true}
              >
                {top3Themes.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ backgroundColor: 'rgba(13,17,23,0.9)', borderColor: 'rgba(0,208,156,0.3)', borderRadius: '8px' }}
                itemStyle={{ color: '#fff', fontSize: '12px' }}
              />
              <Legend verticalAlign="bottom" height={36} wrapperStyle={{ fontSize: '12px' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
