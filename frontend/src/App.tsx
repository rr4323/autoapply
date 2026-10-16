import { Route, Routes } from 'react-router-dom'
import { Nav } from './components/Nav'
import { ApplicationsListPage } from './pages/ApplicationsListPage'
import { NewApplicationPage } from './pages/NewApplicationPage'
import { ApplicationDetailPage } from './pages/ApplicationDetailPage'
import { ProfilePage } from './pages/ProfilePage'

export default function App() {
  return (
    <>
      <Nav />
      <main className="main">
        <Routes>
          <Route path="/" element={<ApplicationsListPage />} />
          <Route path="/apply" element={<NewApplicationPage />} />
          <Route path="/applications/:id" element={<ApplicationDetailPage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Routes>
      </main>
    </>
  )
}
