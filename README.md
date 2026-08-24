# Spotify Lyrics Banner

A thin, movable, resizable banner that pins to the top of your screen and shows
time-synced lyrics for whatever's currently playing on Spotify — one line at a
time, sliding in like a slot-machine reel, tinted to match the track's album art.

- Docks to the top of the screen and (on Windows) reserves that space so maximized
  windows sit below it, the same way the taskbar does
- Click a lyric line to jump playback there
- Height auto-fits the current line; drag the corner grip to resize width
- Lyrics are cached locally, so replaying a track loads instantly
- Scroll on the lyric to fix sync if it's off — see below

## "Windows protected your PC" warning

The first time you run the download, Windows SmartScreen will likely show a
blue warning saying the publisher is unknown. To continue: click
**More info**, then **Run anyway**.

This appears because the app isn't code-signed. A code signing certificate
costs a few hundred pounds a year, which isn't realistic for a free hobby
project, so — like most small open-source Windows tools — this one ships
unsigned. SmartScreen also treats any newly released file as unknown until
enough people have downloaded it, so the warning is about the file's
reputation, not about anything it does.

If you'd rather not take that on trust, the full source is in this repo and
you can build the `.exe` yourself with `build_exe.bat` (see below).

## Known issue: desktop icons rearrange while the banner is docked

While the banner is docked at the top, it reserves that strip of screen space
so maximized windows sit below it instead of underneath it. Windows uses a
single shared value for "usable screen area" — maximized windows read it, and
so does the desktop icon grid. So while the banner is running, Windows may
rearrange your desktop icons to fit the smaller area.

Your icons aren't deleted or lost. Closing the banner releases the reserved
space and Windows restores the normal layout.

There's no way to get one behaviour without the other; it's one OS-level
setting. Two options if the icon shuffling bothers you:

- **Turn off the space reservation.** Open
  `%APPDATA%\SpotifyLyricsBanner\config.json` and add `"reserve_space": false`.
  The banner will then overlap maximized windows instead of pushing them down,
  but your desktop icons are left completely alone.
- **Turn off auto-arrange.** Right-click the desktop → View → untick
  "Auto arrange icons". Windows is then less likely to reposition icons when
  the work area changes.

## If the lyrics are out of sync

Lyrics come from community-maintained databases, not Spotify directly — most
tracks are spot-on, but occasionally one specific song's timing is consistently
off (usually because the matched lyrics were timed against a slightly different
edit/version of the track). If that happens:

1. While the song's playing, **scroll up or down on the lyric text** to nudge
   the timing — scroll the direction that makes it catch up to where it should be.
2. Keep scrolling until it lines up. A small "Lyrics sync: +X.XXs" readout
   shows how far you've adjusted it.
3. That's it — the correction is saved automatically and reapplied every time
   you play that song again. It only affects that one track, not the whole app.

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