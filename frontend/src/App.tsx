import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { CommunityPage } from './components/community/CommunityPage'
import { CreateProvider } from './components/create/CreateProvider'
import { HomePage } from './components/HomePage'
import { IntegrationsPage } from './components/IntegrationsPage'
import { LearnReaderPage } from './components/learning/LearnReaderPage'
import { JourneyPage } from './components/journeys/JourneyPage'
import { JourneysPage } from './components/journeys/JourneysPage'
import { KnowledgeSourcesPage } from './components/knowledge/KnowledgeSourcesPage'
import { LibraryPage } from './components/library/LibraryPage'
import { MyLibraryPage } from './components/library/MyLibraryPage'
import { PromptPage } from './components/library/PromptPage'
import { TemplatesPage } from './components/library/TemplatesPage'
import { LearningPage } from './components/learning/LearningPage'
import { ItemPage } from './components/learning/ItemPage'
import { MyLearningPage } from './components/learning/MyLearningPage'
import { AgentDetailPage } from './components/marketplace/AgentDetailPage'
import { AgentsListPage } from './components/marketplace/AgentsListPage'
import { MarketplacePage } from './components/marketplace/MarketplacePage'
import { PillarPage } from './components/PillarPage'
import { SearchPage } from './components/SearchPage'
import { SuperAgentPage } from './components/SuperAgentPage'
import { Sidebar } from './components/Sidebar'
import { HelpPage, NotFound, SettingsPage } from './components/SimplePages'
import { TopBar } from './components/TopBar'
import { SignIn } from './components/SignIn'
import { ApiError, fetchHome, isAbort } from './lib/api'
import { HubContext } from './lib/hub'
import { PersonaProvider } from './lib/persona'
import type { HomeData } from './lib/types'
import './library.css'

type LoadState =
  { status: 'loading' } | { status: 'signed-out' } | { status: 'error'; message: string } | { status: 'ready'; data: HomeData }

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [pathname])
  return null
}

/** Old documentation and architecture links land on the agent's page, where its documents are linked. */
function ToAgent() {
  const { id = '' } = useParams()
  return <Navigate to={`/marketplace/agents/${encodeURIComponent(id)}`} replace />
}

function Skeleton() {
  return (
    <div className="content" aria-busy="true" aria-label="Loading">
      <div className="skeleton" style={{ height: 44, marginBottom: 28 }} />
      <div className="skeleton" style={{ height: 52, width: 360, marginBottom: 12 }} />
      <div className="skeleton" style={{ height: 24, width: 520, marginBottom: 28 }} />
      <div className="priority-grid">
        <div className="skeleton" style={{ height: 224 }} />
        <div className="skeleton" style={{ height: 224 }} />
        <div className="skeleton" style={{ height: 224 }} />
      </div>
    </div>
  )
}

function Shell({ state, retry }: { state: LoadState; retry: () => void }) {
  const pillars = state.status === 'ready' ? state.data.pillars : []
  const [navOpen, setNavOpen] = useState(false)
  const { pathname } = useLocation()

  // Navigating is the point of the drawer, so close it once the route changes.
  useEffect(() => setNavOpen(false), [pathname])

  // Stop the page behind the drawer from scrolling under the user's finger.
  useEffect(() => {
    if (!navOpen) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [navOpen])

  return (
    <div className="shell">
      <ScrollToTop />
      <div className="frame">
        <Sidebar pillars={pillars} open={navOpen} onClose={() => setNavOpen(false)} />
        <main className="main">
          {state.status === 'loading' && <Skeleton />}
          {state.status === 'error' && (
            <div className="state state--error" role="alert">
              <p className="state__title">The AI Hub is unavailable right now.</p>
              <p>We couldn't reach the MUFG AI Hub service. Try again in a moment.</p>
              <button type="button" className="btn btn--blue btn--inline" onClick={retry}>
                Retry
              </button>
              <p className="state__detail">{state.message}</p>
            </div>
          )}
          {state.status === 'ready' && (
            <HubContext.Provider value={state.data}>
              <PersonaProvider key={state.data.user.id} derived={state.data.user.persona}>
                <CreateProvider>
                <TopBar user={state.data.user} onMenu={() => setNavOpen(true)} />
                <Routes>
                  <Route path="/" element={<HomePage />} />
                  <Route path="/super-agent" element={<SuperAgentPage />} />
                  <Route path="/help" element={<HelpPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/marketplace" element={<MarketplacePage />} />
                  <Route path="/marketplace/agents" element={<AgentsListPage />} />
                  <Route path="/marketplace/solutions" element={<AgentsListPage />} />
                  <Route path="/marketplace/capabilities" element={<AgentsListPage />} />
                  <Route path="/marketplace/agents/:id" element={<AgentDetailPage />} />
                  <Route path="/marketplace/agents/:id/docs" element={<ToAgent />} />
                  <Route path="/marketplace/agents/:id/architecture" element={<ToAgent />} />
                  <Route path="/learning" element={<LearningPage />} />
                  <Route path="/learning/catalog" element={<LearningPage />} />
                  <Route path="/learning/paths" element={<LearningPage />} />
                  <Route path="/learning/best-practices" element={<LearningPage />} />
                  <Route path="/learning/docs" element={<LearningPage />} />
                  <Route path="/learning/quick-reference" element={<LearningPage />} />
                  <Route path="/learning/me" element={<MyLearningPage />} />
                  <Route path="/learning/read" element={<LearnReaderPage />} />
                  <Route path="/community" element={<CommunityPage />} />
                  <Route path="/community/*" element={<CommunityPage />} />
                  <Route path="/integrations" element={<IntegrationsPage />} />
                  <Route path="/search" element={<SearchPage />} />
                  <Route path="/learning/items/:id" element={<ItemPage />} />
                  <Route path="/learning/videos/:id" element={<ItemPage />} />
                  <Route path="/journeys" element={<JourneysPage />} />
                  <Route path="/journeys/:id" element={<JourneyPage />} />
                  <Route path="/library" element={<LibraryPage />} />
                  <Route path="/library/prompts" element={<LibraryPage />} />
                  <Route path="/library/prompts/:id" element={<PromptPage />} />
                  <Route path="/library/templates" element={<TemplatesPage />} />
                  <Route path="/library/mine" element={<MyLibraryPage />} />
                  <Route path="/knowledge/sources" element={<KnowledgeSourcesPage />} />
                  <Route path="/:base/*" element={<PillarPage />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
                </CreateProvider>
              </PersonaProvider>
            </HubContext.Provider>
          )}
        </main>
      </div>
    </div>
  )
}

export default function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const signedOut = () => setState({ status: 'signed-out' })
    window.addEventListener('creditwiz:signed-out', signedOut)
    const storage = (event: StorageEvent) => {
      if (event.key === 'mufg.session-change') signedOut()
    }
    window.addEventListener('storage', storage)
    return () => {
      window.removeEventListener('creditwiz:signed-out', signedOut)
      window.removeEventListener('storage', storage)
    }
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    fetchHome(ctrl.signal)
      .then((data) => setState({ status: 'ready', data }))
      .catch((err: unknown) => {
        if (isAbort(err)) return
        if (err instanceof ApiError && err.status === 401) {
          setState({ status: 'signed-out' })
          return
        }
        setState({ status: 'error', message: err instanceof Error ? err.message : String(err) })
      })
    return () => ctrl.abort()
  }, [attempt])

  return (
    <BrowserRouter>
      {state.status === 'signed-out' ? (
        <SignIn
          onSignIn={() => {
            setState({ status: 'loading' })
            setAttempt((a) => a + 1)
          }}
        />
      ) : (
        <Shell
          state={state}
          retry={() => {
            setState({ status: 'loading' })
            setAttempt((a) => a + 1)
          }}
        />
      )}
    </BrowserRouter>
  )
}
