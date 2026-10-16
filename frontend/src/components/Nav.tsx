import { NavLink } from 'react-router-dom'

export function Nav() {
  return (
    <header className="nav">
      <div className="nav__brand">AgentOS</div>
      <nav className="nav__links">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
          Applications
        </NavLink>
        <NavLink to="/apply" className={({ isActive }) => (isActive ? 'active' : '')}>
          Apply
        </NavLink>
        <NavLink to="/profile" className={({ isActive }) => (isActive ? 'active' : '')}>
          Profile
        </NavLink>
      </nav>
    </header>
  )
}
