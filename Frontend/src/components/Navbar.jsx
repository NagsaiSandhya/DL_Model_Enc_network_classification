import { NavLink } from 'react-router-dom';

export default function Navbar() {
  return (
    <nav className="nav">
      <div className="nav-inner">
        <NavLink to="/" className="nav-title">
          Traffic Classifier
        </NavLink>
        <div className="nav-links">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Dashboard
          </NavLink>
          <NavLink to="/analyze" className={({ isActive }) => (isActive ? 'active' : '')}>
            Analyze Traffic
          </NavLink>
          <NavLink to="/history" className={({ isActive }) => (isActive ? 'active' : '')}>
            Analysis History
          </NavLink>
          <NavLink to="/about" className={({ isActive }) => (isActive ? 'active' : '')}>
            About Project
          </NavLink>
        </div>
      </div>
    </nav>
  );
}
