import React, { useState, useEffect } from 'react';
import OccupancyChart from './OccupancyChart';
import SeatMapper from './SeatMapper';
import SeatHistoryTimeline from './SeatHistoryTimeline';
import { 
  subscribeToOccupancy, 
  fetchAvailableVideos, 
  changeStreamSource, 
  uploadVideoStream, 
  exportSeatsCSV,
  startLiveStream,
  stopLiveStream,
  API_BASE_URL 
} from '../../api/liveApi';
import styles from './Dashboard.module.css';

function formatLiveDuration(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }
  const totalMinutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (totalMinutes < 60) {
    return `${totalMinutes}m ${seconds}s`;
  }
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${hours}h ${minutes}m`;
}

export default function Dashboard() {
  const [seats, setSeats] = useState([]);
  const [systemError, setSystemError] = useState(null);
  const [isStreamActive, setIsStreamActive] = useState(false);
  
  // Dynamic stream selector states
  const [availableVideos, setAvailableVideos] = useState([]);
  const [selectedVideo, setSelectedVideo] = useState("0");
  const [isUploading, setIsUploading] = useState(false);
  
  // Managing chart history queues to visualize timeline trends dynamically
  const [timelineLabels, setTimelineLabels] = useState([]);
  const [timelineData, setTimelineData] = useState([]);

  // Stream preview key helper to force image reload if stream source restarts
  const [streamUrlKey, setStreamUrlKey] = useState(Date.now());

  // WebSocket status state
  const [wsStatus, setWsStatus] = useState("CONNECTED");

  // React state to track timestamps when seats become occupied
  const [occupiedTimestamps, setOccupiedTimestamps] = useState({});

  // 1-second interval ticker for duration ticking
  const [ticker, setTicker] = useState(0);

  // Stream status: "loading" | "loaded" | "error"
  const [streamStatus, setStreamStatus] = useState("loading");
  const [retryTick, setRetryTick] = useState(0);

  // Seat Mapping Mode
  const [isMappingMode, setIsMappingMode] = useState(false);

  // CSV Export Status
  const [csvExporting, setCsvExporting] = useState(false);
  const [csvExportedText, setCsvExportedText] = useState(false);

  // 1-second duration ticker
  useEffect(() => {
    const timer = setInterval(() => {
      setTicker(t => t + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Stream error recovery retry
  useEffect(() => {
    if (streamStatus !== "error") return;

    const timer = setTimeout(() => {
      setRetryTick(prev => prev + 1);
    }, 3000);

    return () => clearTimeout(timer);
  }, [streamStatus, retryTick]);

  useEffect(() => {
    // 1. Fetch initially available video list
    fetchAvailableVideos()
      .then(videos => setAvailableVideos(videos))
      .catch(err => console.error("Failed to load sample videos:", err));

    // 2. Initialize real-time data WebSocket stream
    const ws = subscribeToOccupancy(
      // Success Pipeline
      (data) => {
        setSystemError(null); 
        setSeats(data.seats);

        // Update occupied timestamps dynamically
        setOccupiedTimestamps(prev => {
          const next = { ...prev };
          data.seats.forEach(seat => {
            if (seat.status === 'occupied') {
              if (!next[seat.seat_id]) {
                next[seat.seat_id] = Date.now() - (seat.duration || 0) * 1000;
              }
            } else if (seat.status === 'vacant') {
              delete next[seat.seat_id];
            }
          });
          return next;
        });

        const timeStr = new Date(data.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
        
        const occupiedCount = data.seats.filter(s => s.status === "occupied").length;
        
        setTimelineLabels(prev => {
          const next = [...prev, timeStr];
          return next.slice(-10800); // 3-hour limit (10800 seconds)
        });
        
        setTimelineData(prev => {
          const next = [...prev, occupiedCount];
          return next.slice(-10800); // 3-hour limit
        });
      },
      // Error Pipeline
      (errorMessage) => {
        setSystemError(errorMessage);
        setSeats(prev => prev.map(s => ({ ...s, status: 'unknown' })));
      },
      // Status Pipeline
      (status) => {
        setWsStatus(status);
      }
    );

    return () => {
      ws.close();
    };
  }, []);

  const handleVideoChange = async (e) => {
    const video = e.target.value;
    setSelectedVideo(video);
    try {
      setStreamStatus("loading");
      await changeStreamSource(video);
      // Force preview image element to refresh its feed
      setStreamUrlKey(Date.now());
    } catch (err) {
      alert("Failed to switch video source: " + err.message);
      setStreamStatus("error");
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    setStreamStatus("loading");
    try {
      const res = await uploadVideoStream(file);
      if (res.status === "success") {
        // Refresh dropdown video listing
        const videos = await fetchAvailableVideos();
        setAvailableVideos(videos);
        setSelectedVideo(file.name);
        setStreamUrlKey(Date.now());
      } else {
        alert("Upload error: " + res.message);
        setStreamStatus("error");
      }
    } catch (err) {
      alert("Failed to upload video file: " + err.message);
      setStreamStatus("error");
    } finally {
      setIsUploading(false);
    }
  };

  const handleExportCSV = async () => {
    try {
      setCsvExporting(true);
      const blob = await exportSeatsCSV();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "chronosdesk_export.csv";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      setCsvExportedText(true);
      setTimeout(() => {
        setCsvExportedText(false);
      }, 2000);
    } catch (err) {
      alert("Failed to export transition ledger: " + err.message);
    } finally {
      setCsvExporting(false);
    }
  };

  const totalMapped = seats.length;
  const liveOccupied = seats.filter(s => s.status === 'occupied').length;
  const utilization = totalMapped > 0 ? `${Math.round((liveOccupied / totalMapped) * 100)}%` : "—";
  
  const streamSrc = streamStatus === "error"
    ? `${API_BASE_URL}/stream/live?key=${streamUrlKey}&t=${retryTick}`
    : `${API_BASE_URL}/stream/live?key=${streamUrlKey}`;

  return (
    <div className={styles.dashboardLayout}>
      {/* Top Banner Navigation */}
      <header className={styles.header}>
        <div className={styles.brand}>ChronosDesk<span className={styles.brandAccent}>.AI</span></div>
        
        {/* Stream Source Controls */}
        <div className={styles.controls}>
          <button 
            onClick={async () => {
              if (isStreamActive) {
                await stopLiveStream();
                setIsStreamActive(false);
              } else {
                await startLiveStream();
                setIsStreamActive(true);
              }
            }} 
            className={styles.exportBtn} 
          >
            {isStreamActive ? "Turn Off Camera" : "Turn On Camera"}
          </button>

          <button 
            onClick={handleExportCSV} 
            className={styles.exportBtn} 
            disabled={csvExporting}
          >
            {csvExportedText ? "Exported!" : "Export CSV"}
          </button>

          <select value={selectedVideo} onChange={handleVideoChange} className={styles.dropdown}>
            <option value="0">Default Webcam (Device 0)</option>
            {availableVideos.map(vid => (
              <option key={vid} value={vid}>{vid}</option>
            ))}
          </select>

          <label className={styles.uploadBtn}>
            {isUploading ? "Uploading..." : "Upload MP4"}
            <input 
              type="file" 
              accept="video/mp4" 
              onChange={handleFileUpload} 
              disabled={isUploading} 
              style={{ display: 'none' }} 
            />
          </label>
        </div>

        <div className={styles.statusIndicator}>
           {wsStatus === "CONNECTED" && (
             <span className={styles.liveText}>LIVE NEURAL LINK</span>
           )}
           {wsStatus === "RECONNECTING" && (
             <span className={styles.reconnectingText}>RECONNECTING…</span>
           )}
           {wsStatus === "DISCONNECTED" && (
             <span className={styles.disconnectedText}>DISCONNECTED</span>
           )}
        </div>
      </header>

      {/* Main Orchestration Grid */}
      <main className={styles.mainContent}>
        {/* Left Column: Live Video Feed and Trends */}
        <div className={styles.leftColumn}>
           {/* Video Feed Preview Frame */}
           <div className={styles.previewContainer}>
             <div className={styles.panelHeader}>
               <h3 className={styles.panelTitle}>AI Processed Feed</h3>
               <button 
                 onClick={() => setIsMappingMode(!isMappingMode)} 
                 className={`${styles.mapSeatsBtn} ${isMappingMode ? styles.active : ''}`}
               >
                 {isMappingMode ? "Exit Mapping" : "Map Seats"}
               </button>
             </div>

             {isMappingMode ? (
               <SeatMapper onClose={() => setIsMappingMode(false)} />
             ) : (
               <div className={styles.videoWrapper}>
                 {!isStreamActive ? (
                   <div className={styles.streamSkeleton} style={{ backgroundColor: '#111827', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                     <span className={styles.skeletonText} style={{ opacity: 0.5 }}>Camera Offline</span>
                   </div>
                 ) : (
                   <>
                     {streamStatus === "loading" && (
                       <div className={styles.streamSkeleton}>
                         <div className={styles.skeletonPulse}></div>
                         <span className={styles.skeletonText}>Loading AI Stream...</span>
                       </div>
                     )}
                     {streamStatus === "error" && (
                       <div className={styles.streamErrorOverlay}>
                         <span className={styles.errorOverlayText}>Stream unavailable — retrying…</span>
                       </div>
                     )}
                     <img 
                       src={streamSrc} 
                       alt="Annotated CV Live Frame Stream" 
                       className={`${styles.videoFeed} ${streamStatus === 'loaded' ? styles.visible : styles.hidden}`}
                       onLoad={() => setStreamStatus("loaded")}
                       onError={() => setStreamStatus("error")}
                     />
                   </>
                 )}
               </div>
             )}
           </div>

           <OccupancyChart labels={timelineLabels} dataPoints={timelineData} totalMapped={totalMapped} />
        </div>

        {/* Right Column: Spatial Seating and Analytics */}
        <div className={styles.rightColumn}>
           <div className={styles.statsPanel}>
             <div className={styles.statBox}>
               <h4>Total Mapped</h4>
               <p>{totalMapped}</p>
             </div>
             <div className={styles.statBox}>
               <h4>Live Occupied</h4>
               <p className={styles.highlight}>{liveOccupied}</p>
             </div>
             <div className={styles.statBox}>
               <h4>Utilization</h4>
               <p className={styles.highlight}>{utilization}</p>
             </div>
           </div>

          <div className={styles.seatGridContainer}>
            <h3 className={styles.panelTitle}>Mapped Seating Layout</h3>
            {seats.length === 0 ? (
               <div className={styles.emptyState}>
                 Network standing by. Detecting active chairs in the workspace...
               </div>
            ) : (
               <table className={styles.historyTable}>
                 <thead>
                   <tr>
                     <th>Chair ID</th>
                     <th>Current Status</th>
                     <th>History & Analytics</th>
                   </tr>
                 </thead>
                 <tbody>
                    {seats.map((seat) => {
                      const id = seat.seat_id;
                      
                      return (
                        <tr key={id}>
                          <td className={styles.boldCell}>{seat.display_name}</td>
                          <td>
                            <span className={`${styles.statusBadge} ${styles[seat.status]}`}>
                              {seat.status}
                            </span>
                          </td>
                          <td className={styles.historyCell}>
                            <SeatHistoryTimeline seatId={id} />
                          </td>
                        </tr>
                      );
                    })}
                 </tbody>
               </table>
            )}
          </div>

        </div>
      </main>
    </div>
  );
}
