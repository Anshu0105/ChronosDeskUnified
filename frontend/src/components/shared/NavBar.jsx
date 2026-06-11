import React from 'react';
import { NavLink } from 'react-router-dom';
import styles from './NavBar.module.css';

export default function NavBar() {
  return (
    <nav className={styles.navbar}>
      <div className={styles.brand}>ChronosDesk</div>
      <div className={styles.navLinks}>
        <NavLink 
          to="/" 
          className={({ isActive }) => isActive ? `${styles.link} ${styles.active}` : styles.link}
        >
          Live Monitor
        </NavLink>
        <NavLink 
          to="/recorded" 
          className={({ isActive }) => isActive ? `${styles.link} ${styles.active}` : styles.link}
        >
          Recorded Footage
        </NavLink>
      </div>
    </nav>
  );
}
