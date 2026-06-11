import React, { useRef, useState, useEffect } from 'react';
import { fetchSeats, registerSeat, deleteSeat, API_BASE_URL } from '../../api/liveApi';
import styles from './SeatMapper.module.css';

export default function SeatMapper({ onClose }) {
  const [frameUrl, setFrameUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [imageObj, setImageObj] = useState(null);
  const [registeredSeats, setRegisteredSeats] = useState([]);
  const [pendingSeats, setPendingSeats] = useState([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState({ x: 0, y: 0 });
  const [currentPos, setCurrentPos] = useState({ x: 0, y: 0 });

  const canvasRef = useRef(null);
  const frameUrlRef = useRef(null);

  // 1. Fetch live registered seats on mount
  useEffect(() => {
    async function loadRegisteredSeats() {
      try {
        const seats = await fetchSeats();
        setRegisteredSeats(seats);
      } catch (err) {
        console.error("Failed to load registered seats:", err);
      }
    }
    loadRegisteredSeats();
  }, []);

  // 2. Fetch single JPEG frame from live stream by aborting request once the first complete JPEG is parsed
  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    async function getFrame() {
      try {
        const response = await fetch(`${API_BASE_URL}/stream/live`, {
          signal: controller.signal
        });
        const reader = response.body.getReader();
        let receivedLength = 0;
        let chunks = [];

        while (active) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value);
          receivedLength += value.length;

          // Concatenate chunks
          const concatenated = new Uint8Array(receivedLength);
          let offset = 0;
          for (const chunk of chunks) {
            concatenated.set(chunk, offset);
            offset += chunk.length;
          }

          // Search for SOI (0xFFD8) and EOI (0xFFD9)
          let soiIdx = -1;
          for (let i = 0; i < concatenated.length - 1; i++) {
            if (concatenated[i] === 0xFF && concatenated[i + 1] === 0xD8) {
              soiIdx = i;
              break;
            }
          }

          if (soiIdx !== -1) {
            let eoiIdx = -1;
            for (let i = soiIdx + 2; i < concatenated.length - 1; i++) {
              if (concatenated[i] === 0xFF && concatenated[i + 1] === 0xD9) {
                eoiIdx = i + 1;
                break;
              }
            }

            if (eoiIdx !== -1) {
              const jpegBytes = concatenated.subarray(soiIdx, eoiIdx + 1);
              const blob = new Blob([jpegBytes], { type: 'image/jpeg' });
              const url = URL.createObjectURL(blob);
              if (active) {
                frameUrlRef.current = url;
                setFrameUrl(url);
                setLoading(false);
              }
              controller.abort();
              break;
            }
          }
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error("Failed to parse frozen frame from stream:", err);
          if (active) setLoading(false);
        }
      }
    }

    getFrame();

    return () => {
      active = false;
      controller.abort();
      if (frameUrlRef.current) {
        URL.revokeObjectURL(frameUrlRef.current);
      }
    };
  }, []);

  // 3. Render loop trigger when drawings, sizes, or positions shift
  useEffect(() => {
    if (!imageObj) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // Clear and draw image
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(imageObj, 0, 0);

    // Draw registered seats (green border, transparent fill)
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#10b981';
    ctx.fillStyle = 'rgba(16, 185, 129, 0.1)';
    registeredSeats.forEach(seat => {
      const [x1, y1, x2, y2] = seat.bbox;
      ctx.beginPath();
      ctx.rect(x1, y1, x2 - x1, y2 - y1);
      ctx.fill();
      ctx.stroke();
    });

    // Draw pending seats (blue border, translucent fill)
    ctx.strokeStyle = '#2563eb';
    ctx.fillStyle = 'rgba(37, 99, 235, 0.15)';
    pendingSeats.forEach(seat => {
      const [x1, y1, x2, y2] = seat.bbox;
      ctx.beginPath();
      ctx.rect(x1, y1, x2 - x1, y2 - y1);
      ctx.fill();
      ctx.stroke();
    });

    // Draw current active drawing rectangle
    if (isDrawing) {
      const x1 = Math.min(startPos.x, currentPos.x);
      const y1 = Math.min(startPos.y, currentPos.y);
      const x2 = Math.max(startPos.x, currentPos.x);
      const y2 = Math.max(startPos.y, currentPos.y);
      ctx.beginPath();
      ctx.rect(x1, y1, x2 - x1, y2 - y1);
      ctx.fill();
      ctx.stroke();
    }
  }, [imageObj, registeredSeats, pendingSeats, isDrawing, startPos, currentPos]);

  // Image load success callback
  const handleImageLoad = (e) => {
    const img = e.target;
    const canvas = canvasRef.current;
    if (canvas) {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
    }
    setImageObj(img);
  };

  // Convert viewport client/offset coordinates to original image coordinates
  const getNaturalCoords = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();

    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const naturalX = (x / rect.width) * canvas.width;
    const naturalY = (y / rect.height) * canvas.height;

    return {
      x: Math.max(0, Math.min(canvas.width, naturalX)),
      y: Math.max(0, Math.min(canvas.height, naturalY))
    };
  };

  // Mouse Handlers for Canvas Drawing
  const handleMouseDown = (e) => {
    if (!imageObj) return;
    const coords = getNaturalCoords(e);
    setIsDrawing(true);
    setStartPos(coords);
    setCurrentPos(coords);
  };

  const handleMouseMove = (e) => {
    if (!isDrawing) return;
    const coords = getNaturalCoords(e);
    setCurrentPos(coords);
  };

  const handleMouseUp = (e) => {
    if (!isDrawing) return;
    setIsDrawing(false);
    const coords = getNaturalCoords(e);

    const x1 = Math.min(startPos.x, coords.x);
    const y1 = Math.min(startPos.y, coords.y);
    const x2 = Math.max(startPos.x, coords.x);
    const y2 = Math.max(startPos.y, coords.y);

    // Require a minimum size to avoid accidental small clicks
    if (x2 - x1 > 8 && y2 - y1 > 8) {
      setPendingSeats(prev => [...prev, {
        display_name: "",
        bbox: [x1, y1, x2, y2]
      }]);
    }
  };

  const handleDeleteRegistered = async (seatId) => {
    try {
      await deleteSeat(seatId);
      setRegisteredSeats(prev => prev.filter(s => s.seat_id !== seatId));
    } catch (err) {
      alert("Failed to delete seat: " + err.message);
    }
  };

  const handleDeletePending = (index) => {
    setPendingSeats(prev => prev.filter((_, i) => i !== index));
  };

  const handleRenamePending = (index, newName) => {
    setPendingSeats(prev => prev.map((s, i) => i === index ? { ...s, display_name: newName } : s));
  };

  const handleClearAll = () => {
    setPendingSeats([]);
  };

  const handleConfirm = async () => {
    try {
      await Promise.all(
        pendingSeats.map(seat => registerSeat(seat.display_name, seat.bbox))
      );
      onClose();
    } catch (err) {
      alert("Failed to register seat mapping configurations: " + err.message);
    }
  };

  const naturalWidth = imageObj ? imageObj.naturalWidth : 1;
  const naturalHeight = imageObj ? imageObj.naturalHeight : 1;

  return (
    <div className={styles.mapperWrapper}>
      {loading && (
        <div className={styles.mapperSkeleton}>
          <div className={styles.pulse}></div>
          <span>Capturing Live Feed Snapshot...</span>
        </div>
      )}

      {frameUrl && (
        <img 
          src={frameUrl} 
          alt="Frozen Stream Frame" 
          onLoad={handleImageLoad} 
          style={{ display: 'none' }}
        />
      )}

      {imageObj && (
        <div className={styles.canvasContainer}>
          <canvas
            ref={canvasRef}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            className={styles.canvas}
          />

          {/* Absolute HTML Badge Overlays for Registered Seats */}
          {registeredSeats.map((seat) => {
            const [x1, y1, x2, y2] = seat.bbox;
            const left = `${(x1 / naturalWidth) * 100}%`;
            const top = `${(y1 / naturalHeight) * 100}%`;
            return (
              <div 
                key={seat.seat_id} 
                className={`${styles.overlayBadge} ${styles.registeredBadge}`}
                style={{ left, top }}
              >
                <span className={styles.badgeText}>{`Seat ${seat.seat_id}`}</span>
                <button 
                  onClick={() => handleDeleteRegistered(seat.seat_id)} 
                  className={styles.deleteBadgeBtn}
                  title={`Delete Seat ${seat.seat_id}`}
                >
                  ✕
                </button>
              </div>
            );
          })}

          {/* Absolute HTML Badge Overlays for Pending Seats */}
          {pendingSeats.map((seat, index) => {
            const [x1, y1, x2, y2] = seat.bbox;
            const left = `${(x1 / naturalWidth) * 100}%`;
            const top = `${(y1 / naturalHeight) * 100}%`;
            const maxRegisteredId = registeredSeats.reduce((max, s) => s.seat_id > max ? s.seat_id : max, 0);
            const estimatedId = maxRegisteredId + 1 + index;
            return (
              <div 
                key={index} 
                className={`${styles.overlayBadge} ${styles.pendingBadge}`}
                style={{ left, top }}
              >
                <span className={styles.badgeText}>{`Seat ${estimatedId}`}</span>
                <input 
                  type="text" 
                  value={seat.display_name} 
                  onChange={(e) => handleRenamePending(index, e.target.value)}
                  placeholder="Label (optional)"
                  className={styles.badgeInput}
                  onClick={(e) => e.stopPropagation()} // Prevent triggering drawing actions when naming
                  onMouseDown={(e) => e.stopPropagation()}
                />
                <button 
                  onClick={() => handleDeletePending(index)} 
                  className={styles.deleteBadgeBtn}
                  title="Discard Seat Zone"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className={styles.mapperFooter}>
        <div className={styles.instructions}>
          Click & drag to define seat bounding boxes overlaying workspace zones.
        </div>
        <div className={styles.footerActions}>
          <button onClick={handleClearAll} className={styles.clearBtn} disabled={pendingSeats.length === 0}>
            Clear Pending
          </button>
          <button onClick={onClose} className={styles.cancelBtn}>
            Cancel
          </button>
          <button 
            onClick={handleConfirm} 
            className={styles.confirmBtn}
            disabled={pendingSeats.length === 0}
          >
            Confirm ({pendingSeats.length})
          </button>
        </div>
      </div>
    </div>
  );
}
