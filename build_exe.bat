@echo off
REM One-command build: turns spotify_lyrics_widget.py into a single
REM standalone SpotifyLyricsBanner.exe that people can download and run
REM with no Python install required.
REM
REM Run this FROM the folder containing spotify_lyrics_widget.py, on Windows
REM (PyInstaller builds for whatever OS you run it on).

python -m pip install --upgrade pyinstaller spotipy syncedlyrics pillow requests

python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "SpotifyLyricsBanner" ^
    spotify_lyrics_widget.py

echo.
echo Done. Your exe is in the "dist" folder: dist\SpotifyLyricsBanner.exe
echo That single file is what you share/download — no Python needed to run it.
pause
