import React, { useState } from 'react';
import './App.css';

type Screen = 'login' | 'fleet' | 'workspace';
type Tab = 'operations' | 'tmux' | 'direct_line' | 'studio' | 'knowledge_base';

function App() {
  const [currentScreen, setCurrentScreen] = useState<Screen>('login');
  const [activeTab, setActiveTab] = useState<Tab>('operations');

  const handleLogin = () => setCurrentScreen('fleet');
  const handleOpenProject = () => {
    setCurrentScreen('workspace');
    setActiveTab('operations');
  };

  // === SCREENS ===

  const renderLogin = () => (
    <div className="login-screen">
      <div className="login-box">
        <div className="login-title">Yamaç Jr. Nano</div>
        <div className="login-subtitle">Autonomous CLI Orchestrator</div>
        <input type="password" placeholder="Passphrase" className="login-input" />
        <button className="login-button" onClick={handleLogin}>Authenticate</button>
      </div>
    </div>
  );

  const renderFleet = () => (
    <div className="fleet-screen">
      <div className="fleet-header">
        <div>
          <h1 className="fleet-title">Fleet Command Center</h1>
          <div style={{ color: 'var(--text-muted)' }}>Select a project to enter its isolated workspace.</div>
        </div>
        <button className="new-project-btn">+ New Project (PRD Setup)</button>
      </div>

      {/* NEW: Global Quota Dashboard */}
      <div className="quota-dashboard">
        <div className="quota-header">
          <span>Global CLI Surf & Subscription Limits</span>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 'normal' }}>No Pay-As-You-Go. Pure Auth Surfing.</span>
        </div>
        <div className="quota-grid">
          <div className="quota-item">
            <div className="quota-label">
              <span>Gemini Pro (Daily Auth)</span>
              <span style={{ color: 'var(--accent-red)' }}>429 Exhausted</span>
            </div>
            <div className="quota-bar-bg">
              <div className="quota-bar-fill quota-critical" style={{ width: '100%' }}></div>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Daily Limit: 500/500 — Resets in: 02h:45m</div>
          </div>
          
          <div className="quota-item">
            <div className="quota-label">
              <span>Claude Code (5-Hour Quota)</span>
              <span style={{ color: 'var(--accent-amber)' }}>90% Used</span>
            </div>
            <div className="quota-bar-bg">
              <div className="quota-bar-fill quota-warning" style={{ width: '90%' }}></div>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Usage: 45/50 msg — Next cycle: 1h:12m</div>
          </div>
          
          <div className="quota-item">
            <div className="quota-label">
              <span>OpenCode Minimax (Weekly)</span>
              <span style={{ color: 'var(--accent-green)' }}>Available</span>
            </div>
            <div className="quota-bar-bg">
              <div className="quota-bar-fill quota-healthy" style={{ width: '15%' }}></div>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Weekly Token Quota: 15% Burned</div>
          </div>

          <div className="quota-item">
            <div className="quota-label">
              <span>OpenCode GLM (Fallback)</span>
              <span style={{ color: 'var(--accent-green)' }}>Available</span>
            </div>
            <div className="quota-bar-bg">
              <div className="quota-bar-fill quota-healthy" style={{ width: '5%' }}></div>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Weekly Token Quota: 5% Burned</div>
          </div>
        </div>
      </div>

      <div className="fleet-grid">
        <div className="project-card status-sleep" onClick={handleOpenProject}>
          <div className="project-name">Auth-Microservice</div>
          <div className="project-meta">
            <span style={{ color: 'var(--accent-blue)' }}>Sleeping (Quota Exhausted)</span>
            <span>Wakes in 3h</span>
          </div>
        </div>

        <div className="project-card status-working" onClick={handleOpenProject}>
          <div className="project-name">NextJS-Landing</div>
          <div className="project-meta">
            <span style={{ color: 'var(--accent-amber)' }}>CLI Surf / Dev</span>
            <span>OpenCode (Minimax)</span>
          </div>
        </div>

        <div className="project-card status-prod" onClick={handleOpenProject}>
          <div className="project-name">Data-Scraper-Bot</div>
          <div className="project-meta">
            <span style={{ color: 'var(--accent-green)' }}>Deployed to PROD</span>
            <span>Done</span>
          </div>
        </div>
      </div>
    </div>
  );

  const renderWorkspace = () => (
    <div className="workspace-screen">
      <div className="workspace-header">
        <div className="workspace-title-row">
          <div style={{ fontSize: '20px', fontWeight: '700' }}>Auth-Microservice</div>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Engine: Yamaç Jr. Adapter | Status: Sleeping (Cron Active)</div>
        </div>
        <div className="workspace-tabs">
          <div className={`tab ${activeTab === 'operations' ? 'active' : ''}`} onClick={() => setActiveTab('operations')}>
            Operations Board
          </div>
          <div className={`tab ${activeTab === 'tmux' ? 'active' : ''}`} onClick={() => setActiveTab('tmux')}>
            Active Tmux (2 Panes)
          </div>
          <div className={`tab ${activeTab === 'direct_line' ? 'active' : ''}`} onClick={() => setActiveTab('direct_line')}>
            Yamaç Jr. Direct Line <span className="badge">1</span>
          </div>
          <div className={`tab ${activeTab === 'studio' ? 'active' : ''}`} onClick={() => setActiveTab('studio')}>
            Studio (IDE & Git)
          </div>
          <div className={`tab ${activeTab === 'knowledge_base' ? 'active' : ''}`} onClick={() => setActiveTab('knowledge_base')}>
            Knowledge Base
          </div>
        </div>
      </div>

      <div className="workspace-content">
        
        {/* === OPERATIONS BOARD === */}
        {activeTab === 'operations' && (
          <div className="kanban-board">
            <div className="kanban-col">
              <div className="col-title">Autonomous Backlog</div>
              <div className="kanban-card">Implement RBAC Middleware</div>
              <div className="kanban-card">SSH into CPU server and setup Docker</div>
            </div>
            <div className="kanban-col">
              <div className="col-title">In Progress (Agent)</div>
              <div className="kanban-card" style={{ borderColor: 'var(--accent-amber)' }}>
                <div style={{ fontWeight: '500', marginBottom: '4px' }}>Setup Prisma Schema</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Using: opencode --model minimax</div>
              </div>
            </div>
            <div className="kanban-col">
              <div className="col-title">Deployed to PROD</div>
              <div className="kanban-card">Initialize Git & Repo</div>
            </div>
          </div>
        )}

        {/* === TMUX (Max 2 Panes) === */}
        {activeTab === 'tmux' && (
          <div className="tmux-grid">
            <div className="terminal-wrapper">
              <div className="term-header">Pane 1: CLI Surf Engine (Active)</div>
              <div className="term-line"><span className="term-prompt">yamac-jr@gpu:~$</span><span className="term-command">opencode --model minimax "Write Prisma Schema"</span></div>
              <div className="term-line">&gt; Initializing OpenCode with Minimax...</div>
              <div className="term-line">&gt; Generating schema...</div>
              <div className="term-line" style={{ color: '#4ade80' }}>&gt; Schema generated successfully. Running tests on Pane 2.</div>
            </div>
            <div className="terminal-wrapper" style={{ background: '#000', borderLeft: '1px solid #27272a' }}>
              <div className="term-header">Pane 2: Shadow Test / Logs</div>
              <div className="term-line"><span className="term-prompt">yamac-jr@gpu:~$</span><span className="term-command">npm run test:shadow</span></div>
              <div className="term-line">&gt; compiling typescript...</div>
              <div className="term-line term-error">&gt; Error: Duplicate field 'email' in Prisma Schema.</div>
            </div>
          </div>
        )}

        {/* === DIRECT LINE (Chat) === */}
        {activeTab === 'direct_line' && (
          <div className="chat-container">
            <div className="chat-history">
              <div className="chat-msg msg-agent">
                <div className="msg-bubble">
                  <strong>🤖 Yamaç Jr:</strong> Limitler bitti patron. Claude ve Gemini patladı. Ben bir cron kuruyorum, 3 saat sonra uyandıktan sonra Minimax ile devam edeceğim.
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '8px' }}>Today, 14:30</div>
                </div>
              </div>
              <div className="chat-msg msg-agent">
                <div className="msg-bubble">
                  <strong>🤖 Yamaç Jr:</strong> Bu arada `DATABASE_URL_STAGING` adında bir .env değişkenine ihtiyacım var, devam etmeden önce Project .env sekmesine ekler misin?
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '8px' }}>Today, 14:32</div>
                </div>
              </div>
              <div className="chat-msg msg-patron">
                <div className="msg-bubble">
                  Tamamdır, ben .env kısmına ekliyorum şifreyi. Sen uyanınca oradan okursun.
                  <div style={{ fontSize: '11px', color: '#cbd5e1', marginTop: '8px' }}>Just now</div>
                </div>
              </div>
            </div>
            <div className="chat-input-area">
              <input type="text" className="chat-input" placeholder="Message Yamaç Jr..." />
              <button className="chat-send">Send</button>
            </div>
          </div>
        )}

        {/* === STUDIO (IDE & GIT) === */}
        {activeTab === 'studio' && (
          <div className="studio-grid">
            
            {/* File Explorer */}
            <div className="studio-panel" style={{ borderRight: '1px solid var(--border-dim)' }}>
              <div className="studio-header">Project Files</div>
              <div className="studio-content">
                <div className="file-tree-item">📂 src</div>
                <div className="file-tree-item" style={{ paddingLeft: '24px' }}>📄 index.ts</div>
                <div className="file-tree-item modified" style={{ paddingLeft: '24px' }}>📄 auth.ts</div>
                <div className="file-tree-item active" style={{ paddingLeft: '24px' }}>📄 schema.prisma</div>
                <div className="file-tree-item">📂 tests</div>
                <div className="file-tree-item" style={{ paddingLeft: '24px' }}>📄 auth.test.ts</div>
                <div className="file-tree-item">📄 package.json</div>
                <div className="file-tree-item">📄 tsconfig.json</div>
              </div>
            </div>

            {/* Code Editor */}
            <div className="studio-panel">
              <div className="studio-header">
                <span>src/schema.prisma</span>
                <span style={{ color: 'var(--accent-blue)', textTransform: 'none', fontWeight: 'normal' }}>Auto-saving...</span>
              </div>
              <div className="code-editor">
                <div className="code-line"><span className="line-num">1</span> <span style={{ color: '#c678dd' }}>generator</span> client {'{'}</div>
                <div className="code-line"><span className="line-num">2</span> <span style={{ paddingLeft: '24px' }}>provider = <span style={{ color: '#98c379' }}>"prisma-client-js"</span></span></div>
                <div className="code-line"><span className="line-num">3</span> {'}'}</div>
                <div className="code-line"><span className="line-num">4</span> <br/></div>
                <div className="code-line"><span className="line-num">5</span> <span style={{ color: '#7f848e', fontStyle: 'italic' }}>// Implemented by Yamaç Jr. - Added RBAC roles</span></div>
                <div className="code-line"><span className="line-num">6</span> <span style={{ color: '#c678dd' }}>model</span> User {'{'}</div>
                <div className="code-line"><span className="line-num">7</span> <span style={{ paddingLeft: '24px' }}>id        <span style={{ color: '#56b6c2' }}>Int</span>      @id @default(autoincrement())</span></div>
                <div className="code-line"><span className="line-num">8</span> <span style={{ paddingLeft: '24px' }}>email     <span style={{ color: '#56b6c2' }}>String</span>   @unique</span></div>
                <div className="code-line"><span className="line-num">9</span> <span style={{ paddingLeft: '24px', backgroundColor: '#3f2c2c' }}>role      <span style={{ color: '#56b6c2' }}>String</span>   @default(<span style={{ color: '#98c379' }}>"USER"</span>)</span></div>
                <div className="code-line"><span className="line-num">10</span> {'}'}</div>
              </div>
            </div>

            {/* Git Panel */}
            <div className="studio-panel" style={{ borderLeft: '1px solid var(--border-dim)' }}>
              <div className="studio-header">Source Control</div>
              <div className="studio-content">
                <div className="git-panel-container">
                  
                  <div className="git-section-title">
                    <span>Staged Changes</span>
                    <span className="git-badge">1</span>
                  </div>
                  <div className="git-status-item">
                    <div className="git-filename">
                      <span className="git-status-A">A</span>
                      <span>src/schema.prisma</span>
                    </div>
                    <div className="git-actions">
                      <div className="git-action-icon" title="Unstage">-</div>
                    </div>
                  </div>

                  <div className="git-section-title" style={{ marginTop: '24px' }}>
                    <span>Changes</span>
                    <span className="git-badge">2</span>
                  </div>
                  <div className="git-status-item">
                    <div className="git-filename">
                      <span className="git-status-M">M</span>
                      <span>src/auth.ts</span>
                    </div>
                    <div className="git-actions">
                      <div className="git-action-icon" title="Discard">↺</div>
                      <div className="git-action-icon" title="Stage">+</div>
                    </div>
                  </div>
                  <div className="git-status-item">
                    <div className="git-filename">
                      <span className="git-status-D">D</span>
                      <span style={{ textDecoration: 'line-through', color: 'var(--text-muted)' }}>src/legacy-auth.ts</span>
                    </div>
                    <div className="git-actions">
                      <div className="git-action-icon" title="Discard">↺</div>
                      <div className="git-action-icon" title="Stage">+</div>
                    </div>
                  </div>

                  {/* Commit Box */}
                  <div className="git-commit-box">
                    <div className="git-author-info">
                      <div className="git-avatar">Y</div>
                      <div>
                        <div style={{ fontWeight: '600' }}>Yamaç Jr. Agent</div>
                        <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>Autonomous Commit</div>
                      </div>
                    </div>
                    <textarea 
                      className="git-commit-input"
                      placeholder="Message (Ctrl+Enter to commit)"
                      defaultValue="feat(auth): Implemented Prisma RBAC schema"
                    />
                    <div className="git-commit-actions">
                      <button className="git-btn git-btn-secondary">Sync Changes</button>
                      <button className="git-btn git-btn-primary">Commit & Push</button>
                    </div>
                  </div>

                </div>
              </div>
            </div>

          </div>
        )}

        {/* === KNOWLEDGE BASE === */}
        {activeTab === 'knowledge_base' && (
          <div className="knowledge-grid">
            <div className="studio-panel" style={{ border: '1px solid var(--border-dim)', borderRadius: '8px' }}>
              <div className="studio-header">Project Context (RAG)</div>
              <div className="studio-content" style={{ padding: '0' }}>
                <div className="file-tree-item active" style={{ padding: '12px' }}>📄 PRD_Auth_System.md</div>
                <div className="file-tree-item" style={{ padding: '12px' }}>📄 Architecture_Decisions.md</div>
                <div className="file-tree-item" style={{ padding: '12px' }}>🔗 Legacy DB Schema Dump</div>
              </div>
              <div style={{ padding: '12px', borderTop: '1px solid var(--border-dim)' }}>
                <button className="login-button" style={{ padding: '8px', fontSize: '12px' }}>+ Add Context File</button>
              </div>
            </div>

            <div className="studio-panel" style={{ border: '1px solid var(--border-dim)', borderRadius: '8px' }}>
              <div className="studio-header">📄 PRD_Auth_System.md</div>
              <div className="code-editor" style={{ backgroundColor: 'var(--bg-panel)', color: 'var(--text-main)', fontFamily: 'Inter, sans-serif' }}>
                <h1 style={{ marginBottom: '16px', fontSize: '24px' }}>Authentication System PRD</h1>
                <p style={{ marginBottom: '16px', color: 'var(--text-muted)' }}>Last updated by Patron • 2 days ago</p>
                <h3 style={{ marginBottom: '8px' }}>Objective</h3>
                <p style={{ marginBottom: '16px' }}>Implement a robust Role-Based Access Control (RBAC) system using Prisma and JWT. Replace the legacy Express session middleware.</p>
                <h3 style={{ marginBottom: '8px' }}>Agent Instructions</h3>
                <ul style={{ paddingLeft: '20px', marginBottom: '16px' }}>
                  <li>Create User and Role tables in Prisma.</li>
                  <li>Expose login/register endpoints via Next.js API routes.</li>
                  <li>Do NOT use third-party providers (Auth0/Clerk). Build from scratch.</li>
                </ul>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );

  return (
    <div className="app-root">
      {/* Global Navbar */}
      {currentScreen !== 'login' && (
        <nav className="global-nav">
          <div className="nav-brand" onClick={() => setCurrentScreen('fleet')}>
            <div style={{ width: '12px', height: '12px', background: 'var(--text-main)', borderRadius: '2px' }}></div>
            Executive Mission Control
          </div>
          <div className="nav-actions">
            <div className="nav-item">Global Auth / API Keys</div>
            <div className="nav-item">CPU Server Connections</div>
            <div className="nav-user">
              <strong>Patron</strong>
            </div>
          </div>
        </nav>
      )}

      {/* Screen Router */}
      {currentScreen === 'login' && renderLogin()}
      {currentScreen === 'fleet' && renderFleet()}
      {currentScreen === 'workspace' && renderWorkspace()}
    </div>
  );
}

export default App;
