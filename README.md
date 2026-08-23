# Spotify Lyrics Banner

A thin, movable, resizable banner that pins to the top of your screen and shows
time-synced lyrics for whatever's currently playing on Spotify — one line at a
time, sliding in like a slot-machine reel, tinted to match the track's album art.

- Docks to the top of the screen and (on Windows) reserves that space so maximized
  windows sit below it, the same way the taskbar does
- Click a lyric line to jump playback there
- Height auto-fits the current line; drag the corner grip to resize width
- Lyrics are cached locally, so replaying a track loads instantly

## Download (no Python required)

Grab the latest `SpotifyLyricsBanner.exe` from the [Releases](../../releases) page,
save it anywhere, and double-click it to run.

## Run from source instead

```
pip install -r requirements.txt
python spotify_lyrics_widget.py
```

## One-time setup: link your Spotify account

This app needs its own Spotify "Client ID" to talk to the Spotify API — Spotify
requires every app to have one, and (as of 2026) caps how many people can share a
single one, so **each person needs their own free Client ID**. It takes about two
minutes and never needs to be repeated once it's saved.

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   and log in with your normal Spotify account.
2. Click **Create app**. Name/description can be anything.
3. Under **Redirect URIs**, add exactly: `http://127.0.0.1:8888/callback`
4. When asked which API you're using, tick **Web API**. Save.
5. Open the app you just created → **Settings**, and copy the **Client ID** shown there.
6. Open `spotify_lyrics_widget.py` (or the settings the .exe prompts for on first
   run) and paste it into `SPOTIPY_CLIENT_ID`.

The first time you run the app, your browser will open asking you to log in and
click **Allow** — after that, it's remembered and you won't see it again.

## Building the .exe yourself

Run `build_exe.bat` (Windows only) from the project folder. It installs the
needed packages and produces `dist\SpotifyLyricsBanner.exe`.

## Why can't this just work with zero setup?

Spotify tightened its developer platform in 2026: a single shared Client ID is
now capped at 5 linked accounts, and getting an exemption ("Extended Quota Mode")
requires being an organization with an existing, large user base — not something
a small open-source tool can realistically obtain. The per-user Client ID above
is the standard workaround other small Spotify tools use.

## License

MIT — see [LICENSE](LICENSE).
