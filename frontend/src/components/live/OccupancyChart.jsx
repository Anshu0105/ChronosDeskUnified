import React from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Filler,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import styles from './OccupancyChart.module.css';

// Pre-register Chart.js engine dependencies globally for this component
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Filler,
  Legend
);

export default function OccupancyChart({ labels = [], dataPoints = [], totalMapped = 1 }) {
  const [timeRange, setTimeRange] = React.useState("5 min");

  // Determine slice count
  let limit = 300;
  if (timeRange === "30 min") {
    limit = 1800;
  } else if (timeRange === "All") {
    limit = 10800;
  }

  const slicedLabels = labels.slice(-limit);
  const slicedDataPoints = dataPoints.slice(-limit);

  const data = {
    labels: slicedLabels,
    datasets: [
      {
        fill: true,
        label: 'Active Occupancy',
        data: slicedDataPoints,
        borderColor: '#4f46e5', // Vibrant Indigo
        backgroundColor: (context) => {
          const chart = context.chart;
          const { ctx, chartArea } = chart;

          if (!chartArea) return null;
          
          // Generate a smooth vertical gradient dropping from blue down to transparent
          const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          gradient.addColorStop(0, 'rgba(79, 70, 229, 0.2)');
          gradient.addColorStop(1, 'rgba(79, 70, 229, 0.0)');
          return gradient;
        },
        tension: 0.4, // Generates smooth curves
        pointRadius: 0, // Hides tracking dots until hovered
        pointHoverRadius: 6,
        pointBackgroundColor: '#4f46e5',
        borderWidth: 2,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
      duration: 800,
      easing: 'easeOutQuart',
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        backgroundColor: 'rgba(255, 255, 255, 0.9)',
        titleColor: '#0f172a',
        bodyColor: '#334155',
        borderColor: 'rgba(203, 213, 225, 0.8)',
        borderWidth: 1,
        padding: 12,
        displayColors: false,
        titleFont: { family: 'Plus Jakarta Sans', size: 13, weight: '700' },
        bodyFont: { family: 'Plus Jakarta Sans', size: 12 },
        callbacks: {
          label: (context) => `Occupied: ${context.raw} seats`
        }
      },
    },
    interaction: {
      mode: 'nearest',
      axis: 'x',
      intersect: false
    },
    scales: {
      x: {
        grid: {
          display: false,
          drawBorder: false,
        },
        ticks: {
          color: '#64748b',
          maxTicksLimit: 8,
          font: { family: 'Plus Jakarta Sans', size: 11, weight: '500' }
        },
      },
      y: {
        beginAtZero: true,
        max: Math.max(1, totalMapped),
        grid: {
          color: 'rgba(226, 232, 240, 0.6)',
          drawBorder: false,
        },
        ticks: {
          color: '#64748b',
          stepSize: 1,
          font: { family: 'Plus Jakarta Sans', size: 11, weight: '500' }
        },
      },
    },
  };

  return (
    <div className={styles.chartContainer}>
      <div className={styles.chartHeader}>
        <h3 className={styles.chartTitle}>Space Utilization Trends</h3>
        <div className={styles.toggleContainer}>
          {["5 min", "30 min", "All"].map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              className={`${styles.pillButton} ${timeRange === range ? styles.pillButtonActive : ""}`}
            >
              {range}
            </button>
          ))}
        </div>
      </div>
      <div className={styles.canvasWrapper}>
        <Line options={options} data={data} />
      </div>
    </div>
  );
}
