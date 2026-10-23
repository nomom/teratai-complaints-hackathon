# Teratai Complaints Ops: web dashboard

The React app staff and customers use. It is a client of the FastAPI app (`app/api.py`), which does all the access control: officers work the approval queue, fraud analysts the fraud queue, the manager everything, and customers see only their own cases and what was actually sent to them.

## Run it

Needs Node.js 20.19 or newer, and the Python side running (see the repo's [TEAM.md](../docs/team/TEAM.md)):

```powershell
uv run python -m app.worker                          # terminal 1, repo root
uv run python -m uvicorn app.api:app --port 8000     # terminal 2, repo root
cd web
npm install                                          # once, and after package-lock.json changes
npm run dev                                          # terminal 3: http://localhost:5173
```

Logins: `officer1`, `fraud1`, `manager1` (password `1234`). Customers sign up with their customer ID (e.g. `CUS-00150`) on the sign-in page.

The dev server forwards `/api/*` to the API (`API_TARGET`, default `http://localhost:8000`; copy `.env.example` to `.env.local` to change it).

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm test` | Unit and screen tests (Vitest + Testing Library, against an in-memory fake of the API) |
| `npm run lint` | ESLint |
| `npm run typecheck` | TypeScript, no output |
| `npm run build` | Type-check, then a production build in `dist/` |
| `npm run preview` | Serve the production build locally |

Run `npm run lint`, `npm run typecheck` and `npm test` before opening a PR.

## Structure

Feature folders: everything about one part of the product lives together, and shared pieces sit above them.

```
web/
├── index.html, vite.config.ts, tsconfig*.json, eslint.config.js
└── src/
    ├── main.tsx                 entry: mounts <App/>, loads global styles
    ├── app/                     the shell, shared by every feature
    │   ├── App.tsx              router + providers
    │   ├── routes.tsx           the route table (exported, so tests mount it in a memory router)
    │   ├── lazyPages.ts         pages load on first visit (code splitting)
    │   ├── navigation.ts        the pages, their icons and sections, and which role sees which
    │   ├── guards.tsx           RequireAuth, RequirePage (a page outside the role goes to the role's home)
    │   ├── layout/              AppShell (sidebar + content), Sidebar
    │   └── providers/           theme (dark/light), flash messages, query client
    ├── features/
    │   ├── auth/                sign-in, two-step customer sign-up, session (AuthProvider, useAuth)
    │   ├── cases/               staff side: API calls, React Query hooks, queue ordering and SLA,
    │   │                        the case view (summary, actions, tabs), queue/all-cases/intake pages
    │   └── customer/            customer side: My cases (conversations), New complaint
    ├── components/ui/           design-system primitives: Button, Badge, Alert, Card, Field, Select,
    │                            Tabs, Popover, Switch, PageHeader, EmptyState, Spinner
    ├── lib/                     apiClient (fetch + token + ApiError), session storage, formatting
    ├── styles/                  tokens.css (colour, space, type tokens; dark and light), global.css
    └── test/                    setup, fakeApi (the API's role rules, in memory), renderApp
```

Inside a feature: `api.ts` (HTTP calls), `hooks.ts` (React Query), `types.ts`, `lib/` (pure logic, unit-tested), `components/`, `pages/`.

## Conventions

- **Tokens only.** Components use the CSS variables in `src/styles/tokens.css`, never hex values. Dark is the default; `[data-theme="light"]` on `<html>` switches. The palette is the Teratai Ops system (PersonC's design), with a contrast-checked `--border-strong` for control outlines.
- **Status is never colour alone**: every badge and alert has an icon and a text label. Icons come from `lucide-react`; no emoji.
- **Accessible primitives**: listbox, tabs, popover and switch are Radix components (keyboard support included); there is no native `<select>`.
- **Server state lives in React Query** (`features/*/hooks.ts`); after any action, `caseKeys.all` is invalidated so lists, counts and the open case refresh.
- **The API is the authority.** The UI hides pages a role can't use, but every rule is enforced by `app/api.py`.
