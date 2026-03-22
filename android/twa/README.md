# Android TWA setup

This folder contains the Android-side templates for wrapping the existing frontend as a Trusted Web Activity.

Current target values:

- Domain: `https://podcast-maker-nine.vercel.app`
- Android package id: `com.yakovkahanas.podcastmaker`

## What is already prepared

- The frontend now exposes a basic PWA shell:
  - `frontend/public/manifest.webmanifest`
  - `frontend/public/sw.js`
  - `frontend/public/icons/*`
- `frontend/index.html` now links the manifest and mobile metadata needed by installable browsers.

## What you still need before publishing

1. Deploy the frontend on a production HTTPS domain.
2. Keep the Android application id aligned with `com.yakovkahanas.podcastmaker`.
3. Generate a signing key for the Android app.
4. Publish `/.well-known/assetlinks.json` on the same domain.
5. Build the Android wrapper with Bubblewrap or Android Studio.

## Recommended flow with Bubblewrap

1. No global install is required. Use `npx` from the repo root or any working directory:

```bash
npx @bubblewrap/cli --help
```

2. The project-side files are already prepared:

```bash
android/twa/twa-manifest.template.json
android/twa/assetlinks.json.template
frontend/public/.well-known/assetlinks.json
```

3. Make sure the deployed site serves these URLs successfully:

```bash
https://podcast-maker-nine.vercel.app/manifest.webmanifest
https://podcast-maker-nine.vercel.app/.well-known/assetlinks.json
```

4. Initialize the Android wrapper from the deployed manifest:

```bash
npx @bubblewrap/cli init --manifest=https://podcast-maker-nine.vercel.app/manifest.webmanifest
```

5. When Bubblewrap asks for values, use:

- Application id: `com.yakovkahanas.podcastmaker`
- Host: `podcast-maker-nine.vercel.app`
- Start URL: `/`
- Web manifest URL: `https://podcast-maker-nine.vercel.app/manifest.webmanifest`

6. Generate the Android project:

```bash
npx @bubblewrap/cli build
```

## Required hosting file

Your production site must expose:

`https://podcast-maker-nine.vercel.app/.well-known/assetlinks.json`

The repo now includes the production path at:

`frontend/public/.well-known/assetlinks.json`

Before generating the final Android build, replace:

`REPLACE_WITH_YOUR_UPLOAD_KEY_SHA256`

with the SHA-256 fingerprint of the keystore you will sign the Android app with.

## Notes

- TWA works only with HTTPS in production.
- The Android app and the website share the same frontend, routes, and business logic.
- For local development, continue using the existing web app workflow. The Android shell should target the deployed site, not `localhost`.
