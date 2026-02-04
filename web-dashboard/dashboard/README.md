# HealthCopilot Dashboard

React + Vite dashboard for the HealthCopilot nutrition tracking app.

## Environment Variables

For **production** builds, set the following at build time:

| Variable | Description | Required |
|----------|-------------|----------|
| `VITE_PARSE_API_URL` | Production URL of the Parse API (e.g. `https://parse-api-xyz.onrender.com`). Used for fetching ingredients with full nutrition data. If unset, the build defaults to `http://localhost:5001`, which fails in production and forces a fallback to direct PocketBase. | Yes, if Parse API is deployed |

**Development**: When running `npm run dev`, the Vite proxy forwards `/parse-api` to `localhost:5001`, so you do not need to set `VITE_PARSE_API_URL` locally.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.
