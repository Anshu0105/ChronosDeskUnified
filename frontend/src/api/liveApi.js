// Base API endpoint references
export const API_BASE_URL = "http://127.0.0.1:8000/live";
export const WS_BASE_URL = "ws://127.0.0.1:8000/live";

/**
 * Fetch a flat snapshot of all active seats from the server memory.
 * @returns {Promise<Array>} List of seat objects [{seat_id, bbox, status}]
 */
export async function fetchSeats() {
  const response = await fetch(`${API_BASE_URL}/seats`);
  if (!response.ok) {
    throw new Error("Failed to fetch seats structure");
  }
  return response.json();
}

/**
 * Registers a new seat's bounding box coordinates natively dynamically.
 * @param {string} seat_id Unique identifier for the seat (e.g. 'A1')
 * @param {number[]} bbox Array of 4 pixel coordinates [x1, y1, x2, y2]
 * @returns {Promise<Object>} API response confirming registration success
 */
export async function registerSeat(display_name, bbox) {
  const response = await fetch(`${API_BASE_URL}/seats`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ display_name, bbox })
  });
  
  if (!response.ok) {
    throw new Error("Failed to register seat coordinates");
  }
  return response.json();
}

/**
 * Pull the mock continuous historical ISO8601 timeline array.
 * @param {string} seat_id The exact interactive seat queried.
 * @returns {Promise<Array>} Array of {timestamp, status} dictionaries
 */
export async function fetchSeatHistory(seat_id) {
  const response = await fetch(`${API_BASE_URL}/seats/${seat_id}/history`);
  if (!response.ok) {
    throw new Error(`Failed to fetch history for ${seat_id}`);
  }
  return response.json();
}

/**
 * Deletes a seat entirely from backend storage.
 * @param {string} seatId Unique identifier of the seat
 * @returns {Promise<Object>} API response confirming deletion
 */
export async function deleteSeat(seatId) {
  const response = await fetch(`${API_BASE_URL}/seats/${seatId}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(`Failed to delete seat ${seatId}`);
  }
  return response.json();
}

/**
 * Initiates export of the seat transitions ledger as a CSV file.
 * Returns the blob content of the CSV.
 * @returns {Promise<Blob>} The CSV file content as a Blob.
 */
export async function exportSeatsCSV() {
  const response = await fetch(`${API_BASE_URL}/seats/export/csv`);
  if (!response.ok) {
    throw new Error("Failed to export transition ledger");
  }
  return response.blob();
}

/**
 * Fetches available videos from the backend videos/ directory.
 * @returns {Promise<string[]>} List of video filenames.
 */
export async function fetchAvailableVideos() {
  const response = await fetch(`${API_BASE_URL}/stream/videos`);
  if (!response.ok) {
    throw new Error("Failed to fetch available videos");
  }
  return response.json();
}

/**
 * Changes the active video/camera stream source.
 * @param {string} sourceName Name of video file (e.g., 'video.mp4') or '0' for webcam.
 * @returns {Promise<Object>}
 */
export async function changeStreamSource(sourceName) {
  const response = await fetch(`${API_BASE_URL}/stream/source`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ source: sourceName })
  });
  if (!response.ok) {
    throw new Error("Failed to change stream source");
  }
  return response.json();
}

/**
 * Uploads a video file and switches the stream to it.
 * @param {File} file The video file object.
 * @returns {Promise<Object>}
 */
export async function uploadVideoStream(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/stream/upload`, {
    method: "POST",
    body: formData // Content-Type header is handled automatically by fetch for FormData
  });
  if (!response.ok) {
    throw new Error("Failed to upload video stream");
  }
  return response.json();
}

export async function startLiveStream() {
  const response = await fetch(`${API_BASE_URL}/stream/start`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error("Failed to start live stream");
  }
  return response.json();
}

export async function stopLiveStream() {
  const response = await fetch(`${API_BASE_URL}/stream/stop`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error("Failed to stop live stream");
  }
  return response.json();
}

/**
 * Instantiates our core dashboard real-time data pipe.
 * Callbacks strictly enforce our Phase 3 separation of concerns architectural pattern.
 * 
 * @param {function} onData Passed payload structure: {timestamp, seats}
 * @param {function} onError Triggered specifically when CV pipe detects camera failures
 * @returns {WebSocket} The active instance so React hooks can clean it up safely later.
 */
export function subscribeToOccupancy(onData, onError, onStatusChange) {
  let ws = null;
  let attempts = 0;
  let isClosedCleanly = false;
  let reconnectTimer = null;

  function connect() {
    if (isClosedCleanly) return;

    if (onStatusChange) {
      if (attempts > 0) {
        onStatusChange("RECONNECTING");
      }
    }

    ws = new WebSocket(`${WS_BASE_URL}/ws/occupancy`);
    
    ws.onopen = () => {
      attempts = 0;
      if (onStatusChange) onStatusChange("CONNECTED");
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // Determine cleanly if this is a standard geometry tick or an emergency CV failure
        if (data.event === "stream_error") {
          if (onError) onError(data.message);
        } else {
          if (onData) onData(data);
        }
      } catch (err) {
        console.error("ChronosDesk WS Parsing Failure ->", err);
      }
    };
    
    ws.onerror = (err) => {
      console.error("WebSocket error observed:", err);
    };
    
    ws.onclose = () => {
      console.warn("WebSocket closed.");
      if (isClosedCleanly) return;

      attempts++;
      if (attempts > 3) {
        console.error("WebSocket connection failed after 3 attempts. Stopping reconnect.");
        if (onStatusChange) onStatusChange("DISCONNECTED");
        return;
      }

      const delay = Math.min(1000 * Math.pow(2, attempts - 1), 16000);
      console.log(`Reconnecting in ${delay}ms... (attempt ${attempts})`);
      if (onStatusChange) onStatusChange("RECONNECTING");

      reconnectTimer = setTimeout(() => {
        connect();
      }, delay);
    };
  }

  connect();

  return {
    close: () => {
      isClosedCleanly = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
    }
  };
}
