# Android TWA Setup

This folder contains the Android-side templates for wrapping the existing frontend as a Trusted Web Activity.

Current target values:

- Domain: `https://podcast-maker-nine.vercel.app`
- Android package id: `com.yakovkahanas.podcastmaker`

## What Is Already Prepared

- The frontend exposes a basic PWA shell:
  - `frontend/public/manifest.webmanifest`
  - `frontend/public/sw.js`
  - `frontend/public/icons/*`
- `frontend/index.html` links the manifest and mobile metadata needed by installable browsers.

## What You Still Need Before Publishing

1. Deploy the frontend on a production HTTPS domain.
2. Keep the Android application id aligned with `com.yakovkahanas.podcastmaker`.
3. Generate a signing key for the Android app.
4. Publish `/.well-known/assetlinks.json` on the same domain.
5. Build the Android wrapper with Bubblewrap or Android Studio.

## Recommended Flow With Bubblewrap

1. The project-side files are already prepared:

```text
android/twa/twa-manifest.template.json
android/twa/assetlinks.json.template
frontend/public/.well-known/assetlinks.json
```

2. Make sure the deployed site serves these URLs successfully:

```text
https://podcast-maker-nine.vercel.app/manifest.webmanifest
https://podcast-maker-nine.vercel.app/.well-known/assetlinks.json
```

3. Initialize the Android wrapper from the deployed manifest and use these values when prompted:

- Application id: `com.yakovkahanas.podcastmaker`
- Host: `podcast-maker-nine.vercel.app`
- Start URL: `/`
- Web manifest URL: `https://podcast-maker-nine.vercel.app/manifest.webmanifest`

## Required Hosting File

Your production site must expose:

```text
https://podcast-maker-nine.vercel.app/.well-known/assetlinks.json
```

The repo includes the production path at:

```text
frontend/public/.well-known/assetlinks.json
```

Before generating the final Android build, replace:

```text
REPLACE_WITH_YOUR_UPLOAD_KEY_SHA256
```

with the SHA-256 fingerprint of the keystore you will sign the Android app with.

## Notes

- TWA works only with HTTPS in production.
- The Android app and the website share the same frontend, routes, and business logic.
