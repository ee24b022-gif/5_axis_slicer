# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Production deployment

The frontend reads `VITE_API_BASE_URL` at build time and uses it as the base URL for all API requests (axios in `src/api/client.ts`).

**Required production step:** set `VITE_API_BASE_URL` in the frontend hosting environment to the public backend URL, e.g. `https://api.example.com`. Do not hardcode a deployment URL in the code.

- `VITE_API_BASE_URL` takes precedence.
- `VITE_API_URL` is honored as a compatibility fallback.
- Without either variable, requests are relative to the serving origin (`/api`), which works in development via the Vite proxy (`vite.config.ts`).

The backend is started via `bash entrypoint.sh api` (`render.yaml`), which waits for PostgreSQL, runs Alembic migrations, seeds `fractal_5_pro_provisional`, then starts `main:app`. Make sure `DATABASE_URL` (and any secrets) are set in the backend hosting environment.
