import React, { useState, useRef } from 'react';
import { analyzeVideo } from '../../api/recordedApi';

export default function DropZone({ onAnalysisSuccess }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const validateFile = (selectedFile) => {
    if (!selectedFile) return false;
    const validExtensions = ['.mp4', '.mov', '.avi', '.mkv'];
    const fileName = selectedFile.name.toLowerCase();
    const isValid = validExtensions.some(ext => fileName.endsWith(ext));
    if (!isValid) {
      setError("Unsupported file format. Please drop MP4, MOV, AVI, or MKV videos.");
      return false;
    }
    setError(null);
    return true;
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      if (validateFile(droppedFile)) {
        setFile(droppedFile);
      }
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (validateFile(selectedFile)) {
        setFile(selectedFile);
      }
    }
  };

  const triggerFileSelect = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const removeFile = (e) => {
    e.stopPropagation();
    setFile(null);
    setError(null);
  };

  const handleAnalyze = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeVideo(file);
      await onAnalysisSuccess(data.session_id, data.total_seats, data.duration_sec);
    } catch (err) {
      setError(err.message || "An error occurred during video analysis. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card dropzone-container">
      <div 
        className={`dropzone ${dragActive ? 'active' : ''}`}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={triggerFileSelect}
      >
        <input 
          type="file" 
          ref={fileInputRef}
          onChange={handleFileChange}
          style={{ display: 'none' }}
          accept=".mp4,.mov,.avi,.mkv,video/mp4,video/quicktime,video/x-msvideo,video/x-matroska"
        />

        {loading ? (
          <div className="loading-box">
            <div className="spinner"></div>
            <h3>Analyzing video...</h3>
            <p>This runs computer vision inference to detect seats. Please keep this tab open.</p>
          </div>
        ) : (
          <>
            <svg 
              className="dropzone-icon" 
              fill="none" 
              viewBox="0 0 24 24" 
              stroke="currentColor" 
              strokeWidth={1.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
            </svg>
            
            {file ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px', width: '100%' }}>
                <div className="file-selected-box" onClick={(e) => e.stopPropagation()}>
                  <div className="file-info">
                    <svg style={{ width: '24px', height: '24px', color: 'var(--accent)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" />
                    </svg>
                    <span className="file-name" title={file.name}>{file.name}</span>
                  </div>
                  <button className="btn-remove-file" onClick={removeFile} title="Remove file">
                    <svg style={{ width: '20px', height: '20px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
                <button 
                  className="btn btn-primary" 
                  onClick={(e) => {
                    e.stopPropagation();
                    handleAnalyze();
                  }}
                  style={{ width: '100%', maxWidth: '300px' }}
                >
                  Analyze Video
                </button>
              </div>
            ) : (
              <>
                <h3>Drag and drop your video file here</h3>
                <p>Or click to browse from your computer</p>
                <p style={{ marginTop: '8px', fontSize: '0.75rem', opacity: 0.7 }}>
                  Supported formats: MP4, MOV, AVI, MKV
                </p>
              </>
            )}
          </>
        )}

        {error && (
          <div className="error-message" onClick={(e) => e.stopPropagation()}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
