import React from 'react';
import { 
  BarChart as RechartsBarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  ReferenceLine 
} from 'recharts';

// Custom Tooltip component to match the premium dark theme
const CustomTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="recharts-custom-tooltip">
        <p style={{ fontWeight: 'bold' }}>Seat {data.seat_id}</p>
        <p className="percentage">{payload[0].value.toFixed(1)}% occupied</p>
      </div>
    );
  }
  return null;
};

export default function BarChart({ perSeat }) {
  // Format data for Recharts
  const chartData = perSeat.map(seat => ({
    name: `Seat ${seat.seat_id}`,
    occupancy: seat.occupancyPct,
    seat_id: seat.seat_id
  }));

  return (
    <div className="card">
      <h3 className="card-title">Occupancy % per Seat</h3>
      <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <RechartsBarChart
            data={chartData}
            margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
          >
            <defs>
              <linearGradient id="colorUv" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#4f46e5" stopOpacity={1}/>
                <stop offset="100%" stopColor="#818cf8" stopOpacity={1}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis 
              dataKey="name" 
              tick={{ fill: '#64748b', fontSize: 12, fontWeight: 500 }} 
              axisLine={{ stroke: '#e2e8f0' }}
              tickLine={{ stroke: '#e2e8f0' }}
            />
            <YAxis 
              domain={[0, 100]} 
              tickFormatter={(tick) => `${tick}%`}
              tick={{ fill: '#64748b', fontSize: 12, fontWeight: 500 }}
              axisLine={{ stroke: '#e2e8f0' }}
              tickLine={{ stroke: '#e2e8f0' }}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(79, 70, 229, 0.05)' }} />
            
            {/* Reference line at 50% */}
            <ReferenceLine 
              y={50} 
              stroke="#f59e0b" 
              strokeDasharray="4 4" 
              label={{ 
                value: '50% Threshold', 
                fill: '#f59e0b', 
                fontSize: 11,
                fontWeight: 600,
                position: 'top' 
              }} 
            />
            
            <Bar 
              dataKey="occupancy" 
              fill="url(#colorUv)" 
              activeBar={{ fill: '#4338ca' }}
              radius={[6, 6, 0, 0]} 
              maxBarSize={60}
            />
          </RechartsBarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
