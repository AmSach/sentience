"""Spotify Integration - playback, search, playlists."""
import os, json, base64
# removed

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIFY_AVAILABLE = True
except ImportError:
    SPOTIFY_AVAILABLE = False

class SpotifyIntegration:
    def __init__(self, config):
        self.config = config
        self.client = None
    
    def connect(self) -> bool:
        if not SPOTIFY_AVAILABLE:
            return False
        try:
            scope = "user-read-playback-state,user-modify-playback-state,user-library-read,playlist-read-private"
            sp_oauth = SpotifyOAuth(client_id=self.config.secrets.get("client_id"), client_secret=self.config.secrets.get("client_secret"), redirect_uri=self.config.secrets.get("redirect_uri", "http://localhost:8888/callback"), scope=scope)
            token = sp_oauth.get_access_token(as_server=False)
            self.client = spotipy.Spotify(auth=token)
            return True
        except Exception:
            return False
    
    def now_playing(self):
        if not self.client:
            return {"error": "Not connected"}
        try:
            results = self.client.current_user_playing_track()
            if results:
                return {"playing": True, "track": results["item"]["name"], "artist": results["item"]["artists"][0]["name"], "album": results["item"]["album"]["name"]}
            return {"playing": False}
        except Exception as e:
            return {"error": str(e)}
    
    def search(self, query: str, typ: str = "track"):
        if not self.client:
            return {"error": "Not connected"}
        results = self.client.search(q=query, type=typ, limit=10)
        return results
