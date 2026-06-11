import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import NavBar from './components/shared/NavBar';
import LivePage from './pages/LivePage';
import RecordedPage from './pages/RecordedPage';

export default function App() {
  return (
    <BrowserRouter>
      <NavBar />
      <Routes>
        <Route path="/" element={<LivePage />} />
        <Route path="/recorded" element={<RecordedPage />} />
      </Routes>
    </BrowserRouter>
  );
}
