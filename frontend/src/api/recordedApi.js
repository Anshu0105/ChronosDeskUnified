const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const API_BASE_URL = `${baseUrl}/recorded`;
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

export async function analyzeVideo(file) {
  const formData = new FormData();
  formData.append('video', file);
  
  let url = `${API_BASE_URL}/analyze`;
  if (USE_MOCK) {
    url += '?mock=true';
  }
  
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });
  
  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    throw new Error(errData.detail || `Analysis failed with status ${response.status}`);
  }
  
  return await response.json();
}

export async function getSession(id) {
  const response = await fetch(`${API_BASE_URL}/sessions/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch session: ${response.statusText}`);
  }
  return await response.json();
}

export async function getSessions() {
  const response = await fetch(`${API_BASE_URL}/sessions`);
  if (!response.ok) {
    throw new Error(`Failed to fetch sessions: ${response.statusText}`);
  }
  return await response.json();
}
