# IRONLINE ACCESS — Solution Architecture

## How to export as image
1. Open [mermaid.live](https://mermaid.live)
2. Paste the diagram code below
3. Click **PNG** or **SVG** to download

---

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#1c1c2e', 'primaryTextColor': '#ffffff', 'primaryBorderColor': '#E87722', 'lineColor': '#E87722', 'secondaryColor': '#f3f4f6', 'tertiaryColor': '#ffffff'}}}%%

flowchart TB
    classDef user      fill:#E87722,stroke:#c96a1a,color:#fff,font-weight:bold
    classDef cloud     fill:#1c1c2e,stroke:#E87722,color:#fff,font-weight:bold
    classDef module    fill:#2d2d44,stroke:#E87722,color:#fff
    classDef supabase  fill:#3ecf8e,stroke:#2baf74,color:#1c1c2e,font-weight:bold
    classDef db        fill:#f3f4f6,stroke:#9ca3af,color:#111827
    classDef github    fill:#24292e,stroke:#E87722,color:#fff,font-weight:bold

    %% ── User Layer ──────────────────────────────────────────────────────────
    subgraph USER["  USER LAYER  "]
        direction LR
        Browser["🌐 Web Browser"]
        Cookies["🍪 Browser Cookies\nil_at · il_rt\n(JWT — 7 / 30 day TTL)"]
    end

    %% ── CI/CD ───────────────────────────────────────────────────────────────
    GitHub["🐙 GitHub\nerp_system repository\nAuto-deploy on push"]:::github

    %% ── Application Layer ───────────────────────────────────────────────────
    subgraph APP["  STREAMLIT CLOUD  "]
        direction TB

        Entry["app.py\nEntry Point · Routing · Navbar\nCookie session restore"]:::cloud

        subgraph CORE["Core Helpers"]
            direction LR
            Auth["auth.py\nSession state\nRole & page access"]:::module
            SBC["supabase_client.py\nAnon client\nAdmin client\n_secret() helper"]:::module
        end

        subgraph VIEWS["Page Views  (erp/views/)"]
            direction LR
            V1["📊 Dashboard"]:::module
            V2["👥 Customers\nSites · Operators"]:::module
            V3["🏗️ Machines\nAssets"]:::module
            V4["📋 Work Orders"]:::module
            V5["🚚 Deployments\nMob · Demob · Other"]:::module
            V6["📝 Worklog\nWL Report"]:::module
            V7["🔐 Admin\nUsers · Activity Log"]:::module
            V8["🔑 Login"]:::module
        end
    end

    %% ── Supabase Layer ──────────────────────────────────────────────────────
    subgraph SB["  SUPABASE (Backend-as-a-Service)  "]
        direction TB

        SBAuth["🔒 Supabase Auth\nJWT · sign_in\nsign_out · set_session\nadmin.create_user"]:::supabase

        subgraph PGDB["PostgreSQL Database"]
            direction LR
            T1["customers\nsites\noperators"]:::db
            T2["machines\nasset_master"]:::db
            T3["work_orders\nwork_order_lines\ndeployments"]:::db
            T4["work_logs"]:::db
            T5["user_profiles\nactivity_logs"]:::db
        end
    end

    %% ── Connections ─────────────────────────────────────────────────────────
    Browser      <-->|"HTTPS · WebSocket"| Entry
    Cookies      <-->|"Restore / persist\nsession tokens"| Entry
    GitHub       -->|"Auto-deploy\non git push"| APP

    Entry        --> Auth
    Entry        --> VIEWS
    Entry        --> SBC
    Auth         --> SBC
    VIEWS        --> SBC

    SBC          <-->|"REST API\n(anon key · RLS)"| PGDB
    SBC          <-->|"REST API\n(service role key)"| SBAuth
    SBC          <-->|"service role key\nbypasses RLS"| T5
```

---

## Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Frontend | Python · Streamlit 1.36+ |
| Session persistence | streamlit-cookies-controller |
| Database | Supabase PostgreSQL |
| Authentication | Supabase Auth (JWT) |
| ORM / data access | supabase-py (REST) |
| Hosting | Streamlit Community Cloud |
| Source control & CI/CD | GitHub (auto-deploy on push) |
| Config & secrets | Streamlit Cloud Secrets (TOML) |

## Key Features

- **Role-based access control** — Admin sees all pages; User role sees only permitted pages
- **Cookie-based session persistence** — Login survives navbar page reloads
- **Machine deployment workflow** — Mob / Demob / Other with status transitions (Reserved → Mobilizing → On Rent → Demobilizing → Available)
- **Activity audit log** — Every login, user creation, and permission change is recorded
- **Admin panel** — Create users, set page permissions, view full activity log
