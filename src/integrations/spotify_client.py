"""
Spotify Client for Sentience v3.0
Full-featured Spotify integration with OAuth PKCE, playback, and playlists.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import httpx

from .oauth_manager import OAuthManager, OAuthProvider, OAuthError

logger = logging.getLogger(__name__)


SPOTIFY_SCOPES = [
    "user-read-email",
    "user-read-private",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-read-recently-played",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read",
    "user-library-modify",
    "user-follow-read",
    "user-follow-modify",
    "user-top-read",
]


class RepeatState(Enum):
    """Repeat modes."""
    OFF = "off"
    TRACK = "track"
    CONTEXT = "context"


class TimeRange(Enum):
    """Time ranges for top items."""
    SHORT = "short_term"  # ~4 weeks
    MEDIUM = "medium_term"  # ~6 months
    LONG = "long_term"  # Several years


@dataclass
class SpotifyImage:
    """Spotify image."""
    url: str
    height: Optional[int] = None
    width: Optional[int] = None


@dataclass
class SpotifyArtist:
    """Spotify artist."""
    id: str
    name: str
    uri: str
    href: str
    genres: list[str] = field(default_factory=list)
    images: list[SpotifyImage] = field(default_factory=list)
    popularity: int = 0
    followers: int = 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "SpotifyArtist":
        """Create from API response."""
        images = [
            SpotifyImage(url=i["url"], height=i.get("height"), width=i.get("width"))
            for i in data.get("images", [])
        ]

        return cls(
            id=data["id"],
            name=data["name"],
            uri=data["uri"],
            href=data["href"],
            genres=data.get("genres", []),
            images=images,
            popularity=data.get("popularity", 0),
            followers=data.get("followers", {}).get("total", 0),
        )


@dataclass
class SpotifyAlbum:
    """Spotify album."""
    id: str
    name: str
    uri: str
    href: str
    album_type: str
    artists: list[SpotifyArtist] = field(default_factory=list)
    images: list[SpotifyImage] = field(default_factory=list)
    release_date: Optional[str] = None
    total_tracks: int = 0
    tracks: list["SpotifyTrack"] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "SpotifyAlbum":
        """Create from API response."""
        artists = [SpotifyArtist.from_api(a) for a in data.get("artists", [])]
        images = [
            SpotifyImage(url=i["url"], height=i.get("height"), width=i.get("width"))
            for i in data.get("images", [])
        ]

        album = cls(
            id=data["id"],
            name=data["name"],
            uri=data["uri"],
            href=data["href"],
            album_type=data.get("album_type", "album"),
            artists=artists,
            images=images,
            release_date=data.get("release_date"),
            total_tracks=data.get("total_tracks", 0),
        )

        # Parse tracks if present (full album object)
        if "tracks" in data and "items" in data["tracks"]:
            for track_data in data["tracks"]["items"]:
                track_data["album"] = {"id": data["id"], "name": data["name"]}
                album.tracks.append(SpotifyTrack.from_api(track_data))

        return album


@dataclass
class SpotifyTrack:
    """Spotify track."""
    id: str
    name: str
    uri: str
    href: str
    duration_ms: int
    artists: list[SpotifyArtist] = field(default_factory=list)
    album: Optional[SpotifyAlbum] = None
    disc_number: int = 1
    track_number: int = 1
    explicit: bool = False
    popularity: int = 0
    preview_url: Optional[str] = None
    is_playable: bool = True

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "SpotifyTrack":
        """Create from API response."""
        artists = [SpotifyArtist.from_api(a) for a in data.get("artists", [])]

        album = None
        if "album" in data:
            album = SpotifyAlbum.from_api(data["album"])

        return cls(
            id=data["id"],
            name=data["name"],
            uri=data["uri"],
            href=data["href"],
            duration_ms=data.get("duration_ms", 0),
            artists=artists,
            album=album,
            disc_number=data.get("disc_number", 1),
            track_number=data.get("track_number", 1),
            explicit=data.get("explicit", False),
            popularity=data.get("popularity", 0),
            preview_url=data.get("preview_url"),
            is_playable=data.get("is_playable", True),
        )


@dataclass
class SpotifyPlaylist:
    """Spotify playlist."""
    id: str
    name: str
    uri: str
    href: str
    description: Optional[str] = None
    owner: Optional[dict[str, Any]] = None
    public: bool = True
    collaborative: bool = False
    images: list[SpotifyImage] = field(default_factory=list)
    tracks_total: int = 0
    followers: int = 0
    snapshot_id: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "SpotifyPlaylist":
        """Create from API response."""
        images = [
            SpotifyImage(url=i["url"], height=i.get("height"), width=i.get("width"))
            for i in data.get("images", [])
        ]

        return cls(
            id=data["id"],
            name=data["name"],
            uri=data["uri"],
            href=data["href"],
            description=data.get("description"),
            owner=data.get("owner"),
            public=data.get("public", True),
            collaborative=data.get("collaborative", False),
            images=images,
            tracks_total=data.get("tracks", {}).get("total", 0),
            followers=data.get("followers", {}).get("total", 0),
            snapshot_id=data.get("snapshot_id"),
        )


@dataclass
class SpotifyDevice:
    """Spotify playback device."""
    id: str
    name: str
    type: str
    is_active: bool = False
    is_restricted: bool = False
    is_private_session: bool = False
    volume_percent: int = 100

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "SpotifyDevice":
        """Create from API response."""
        return cls(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            is_active=data.get("is_active", False),
            is_restricted=data.get("is_restricted", False),
            is_private_session=data.get("is_private_session", False),
            volume_percent=data.get("volume_percent", 100),
        )


@dataclass
class PlaybackState:
    """Current playback state."""
    is_playing: bool
    progress_ms: int
    repeat_state: RepeatState
    shuffle_state: bool
    device: Optional[SpotifyDevice] = None
    track: Optional[SpotifyTrack] = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "PlaybackState":
        """Create from API response."""
        device = None
        if "device" in data:
            device = SpotifyDevice.from_api(data["device"])

        track = None
        if "item" in data:
            track = SpotifyTrack.from_api(data["item"])

        return cls(
            is_playing=data.get("is_playing", False),
            progress_ms=data.get("progress_ms", 0),
            repeat_state=RepeatState(data.get("repeat_state", "off")),
            shuffle_state=data.get("shuffle_state", False),
            device=device,
            track=track,
        )


@dataclass
class PlaylistTrack:
    """Track in a playlist with additional info."""
    track: SpotifyTrack
    added_at: Optional[datetime] = None
    added_by: Optional[dict[str, Any]] = None
    is_local: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "PlaylistTrack":
        """Create from API response."""
        added_at = None
        if "added_at" in data:
            added_at = datetime.fromisoformat(data["added_at"].replace("Z", "+00:00"))

        return cls(
            track=SpotifyTrack.from_api(data["track"]),
            added_at=added_at,
            added_by=data.get("added_by"),
            is_local=data.get("is_local", False),
        )


class SpotifyClient:
    """
    Full-featured Spotify client with:
    - OAuth + PKCE authentication
    - Playback control (play, pause, skip, etc.)
    - Playlist management
    - Search functionality
    """

    BASE_URL = "https://api.spotify.com/v1"

    def __init__(
        self,
        oauth_manager: OAuthManager,
        user_id: Optional[str] = None,
    ):
        self.oauth_manager = oauth_manager
        self.user_id = user_id
        self._http_client = httpx.AsyncClient(timeout=30.0)

    async def _get_headers(self) -> dict[str, str]:
        """Get authenticated headers."""
        token = await self.oauth_manager.get_or_refresh_token(
            OAuthProvider.SPOTIFY, self.user_id
        )
        return {
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated request to Spotify API."""
        headers = await self._get_headers()
        headers.update(kwargs.pop("headers", {}))
        url = f"{self.BASE_URL}{path}"

        response = await self._http_client.request(
            method, url, headers=headers, **kwargs
        )

        if response.status_code == 401:
            token = await self.oauth_manager.get_or_refresh_token(
                OAuthProvider.SPOTIFY, self.user_id
            )
            headers["Authorization"] = f"Bearer {token.access_token}"
            response = await self._http_client.request(
                method, url, headers=headers, **kwargs
            )

        if response.status_code == 204:
            return {}

        if response.status_code >= 400:
            try:
                error = response.json().get("error", {}).get("message", response.text)
            except Exception:
                error = response.text
            raise SpotifyError(f"Spotify API error: {error}")

        return response.json()

    # ==================== User Profile ====================

    async def get_current_user(self) -> dict[str, Any]:
        """Get current user profile."""
        return await self._request("GET", "/me")

    async def get_user(self, user_id: str) -> dict[str, Any]:
        """Get a user's profile."""
        return await self._request("GET", f"/users/{user_id}")

    # ==================== Playback Control ====================

    async def get_playback_state(self) -> Optional[PlaybackState]:
        """Get current playback state."""
        try:
            data = await self._request("GET", "/me/player")
            if not data:
                return None
            return PlaybackState.from_api(data)
        except SpotifyError:
            return None

    async def get_currently_playing(self) -> Optional[SpotifyTrack]:
        """Get currently playing track."""
        try:
            data = await self._request("GET", "/me/player/currently-playing")
            if not data or "item" not in data:
                return None
            return SpotifyTrack.from_api(data["item"])
        except SpotifyError:
            return None

    async def get_devices(self) -> list[SpotifyDevice]:
        """Get available devices."""
        data = await self._request("GET", "/me/player/devices")
        return [SpotifyDevice.from_api(d) for d in data.get("devices", [])]

    async def play(
        self,
        device_id: Optional[str] = None,
        context_uri: Optional[str] = None,
        uris: Optional[list[str]] = None,
        offset: Optional[int] = None,
        position_ms: Optional[int] = None,
    ) -> bool:
        """
        Start playback.
        context_uri: Album, playlist, or artist URI
        uris: List of track URIs
        offset: Track offset (0-indexed)
        """
        body = {}

        if context_uri:
            body["context_uri"] = context_uri
        elif uris:
            body["uris"] = uris

        if offset is not None:
            body["offset"] = {"position": offset}
        if position_ms is not None:
            body["position_ms"] = position_ms

        params = {}
        if device_id:
            params["device_id"] = device_id

        await self._request(
            "PUT",
            "/me/player/play",
            json=body if body else None,
            params=params if params else None,
        )
        return True

    async def pause(self, device_id: Optional[str] = None) -> bool:
        """Pause playback."""
        params = {}
        if device_id:
            params["device_id"] = device_id

        await self._request("PUT", "/me/player/pause", params=params if params else None)
        return True

    async def next_track(self, device_id: Optional[str] = None) -> bool:
        """Skip to next track."""
        params = {}
        if device_id:
            params["device_id"] = device_id

        await self._request("POST", "/me/player/next", params=params if params else None)
        return True

    async def previous_track(self, device_id: Optional[str] = None) -> bool:
        """Go to previous track."""
        params = {}
        if device_id:
            params["device_id"] = device_id

        await self._request("POST", "/me/player/previous", params=params if params else None)
        return True

    async def seek(self, position_ms: int, device_id: Optional[str] = None) -> bool:
        """Seek to position in current track."""
        params = {"position_ms": position_ms}
        if device_id:
            params["device_id"] = device_id

        await self._request("PUT", "/me/player/seek", params=params)
        return True

    async def set_repeat(
        self,
        state: RepeatState,
        device_id: Optional[str] = None,
    ) -> bool:
        """Set repeat mode."""
        params = {"state": state.value}
        if device_id:
            params["device_id"] = device_id

        await self._request("PUT", "/me/player/repeat", params=params)
        return True

    async def set_shuffle(
        self,
        state: bool,
        device_id: Optional[str] = None,
    ) -> bool:
        """Set shuffle mode."""
        params = {"state": str(state).lower()}
        if device_id:
            params["device_id"] = device_id

        await self._request("PUT", "/me/player/shuffle", params=params)
        return True

    async def set_volume(
        self,
        volume_percent: int,
        device_id: Optional[str] = None,
    ) -> bool:
        """Set volume (0-100)."""
        params = {"volume_percent": min(100, max(0, volume_percent))}
        if device_id:
            params["device_id"] = device_id

        await self._request("PUT", "/me/player/volume", params=params)
        return True

    async def transfer_playback(
        self,
        device_id: str,
        play: bool = False,
    ) -> bool:
        """Transfer playback to another device."""
        await self._request(
            "PUT",
            "/me/player",
            json={"device_ids": [device_id], "play": play},
        )
        return True

    # ==================== Playlist Management ====================

    async def get_playlist(
        self,
        playlist_id: str,
        fields: Optional[str] = None,
    ) -> SpotifyPlaylist:
        """Get a playlist by ID."""
        params = {}
        if fields:
            params["fields"] = fields

        data = await self._request("GET", f"/playlists/{playlist_id}", params=params)
        return SpotifyPlaylist.from_api(data)

    async def list_playlists(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SpotifyPlaylist]:
        """Get user's playlists."""
        params = {"limit": limit, "offset": offset}

        if user_id:
            data = await self._request("GET", f"/users/{user_id}/playlists", params=params)
        else:
            data = await self._request("GET", "/me/playlists", params=params)

        return [SpotifyPlaylist.from_api(p) for p in data.get("items", [])]

    async def create_playlist(
        self,
        name: str,
        user_id: Optional[str] = None,
        description: Optional[str] = None,
        public: bool = True,
        collaborative: bool = False,
    ) -> SpotifyPlaylist:
        """Create a new playlist."""
        if not user_id:
            user = await self.get_current_user()
            user_id = user["id"]

        body = {
            "name": name,
            "public": public,
            "collaborative": collaborative,
        }
        if description:
            body["description"] = description

        data = await self._request("POST", f"/users/{user_id}/playlists", json=body)
        logger.info(f"Created playlist {data['id']}: {name}")
        return SpotifyPlaylist.from_api(data)

    async def update_playlist(
        self,
        playlist_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        public: Optional[bool] = None,
        collaborative: Optional[bool] = None,
    ) -> bool:
        """Update playlist details."""
        body = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if public is not None:
            body["public"] = public
        if collaborative is not None:
            body["collaborative"] = collaborative

        await self._request("PUT", f"/playlists/{playlist_id}", json=body)
        return True

    async def delete_playlist(self, playlist_id: str) -> bool:
        """Unfollow (delete) a playlist."""
        await self._request("DELETE", f"/playlists/{playlist_id}/followers")
        logger.info(f"Deleted playlist {playlist_id}")
        return True

    async def get_playlist_tracks(
        self,
        playlist_id: str,
        limit: int = 100,
        offset: int = 0,
        fields: Optional[str] = None,
    ) -> list[PlaylistTrack]:
        """Get tracks in a playlist."""
        params = {"limit": limit, "offset": offset}
        if fields:
            params["fields"] = fields

        data = await self._request(
            "GET",
            f"/playlists/{playlist_id}/tracks",
            params=params,
        )

        return [PlaylistTrack.from_api(t) for t in data.get("items", [])]

    async def add_tracks_to_playlist(
        self,
        playlist_id: str,
        track_uris: list[str],
        position: Optional[int] = None,
    ) -> str:
        """Add tracks to playlist. Returns snapshot_id."""
        body = {"uris": track_uris}
        if position is not None:
            body["position"] = position

        data = await self._request(
            "POST",
            f"/playlists/{playlist_id}/tracks",
            json=body,
        )
        logger.info(f"Added {len(track_uris)} tracks to playlist {playlist_id}")
        return data["snapshot_id"]

    async def remove_tracks_from_playlist(
        self,
        playlist_id: str,
        track_uris: list[str],
        snapshot_id: Optional[str] = None,
    ) -> str:
        """Remove tracks from playlist. Returns new snapshot_id."""
        body = {"tracks": [{"uri": uri} for uri in track_uris]}
        if snapshot_id:
            body["snapshot_id"] = snapshot_id

        data = await self._request(
            "DELETE",
            f"/playlists/{playlist_id}/tracks",
            json=body,
        )
        logger.info(f"Removed {len(track_uris)} tracks from playlist {playlist_id}")
        return data["snapshot_id"]

    async def replace_playlist_tracks(
        self,
        playlist_id: str,
        track_uris: list[str],
    ) -> bool:
        """Replace all tracks in a playlist."""
        await self._request(
            "PUT",
            f"/playlists/{playlist_id}/tracks",
            json={"uris": track_uris},
        )
        return True

    # ==================== Library ====================

    async def get_saved_tracks(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PlaylistTrack]:
        """Get saved tracks (Liked Songs)."""
        data = await self._request(
            "GET",
            "/me/tracks",
            params={"limit": limit, "offset": offset},
        )
        return [PlaylistTrack.from_api(t) for t in data.get("items", [])]

    async def save_tracks(self, track_ids: list[str]) -> bool:
        """Save tracks to library."""
        await self._request(
            "PUT",
            "/me/tracks",
            json={"ids": track_ids},
        )
        return True

    async def remove_saved_tracks(self, track_ids: list[str]) -> bool:
        """Remove tracks from library."""
        await self._request(
            "DELETE",
            "/me/tracks",
            json={"ids": track_ids},
        )
        return True

    async def check_saved_tracks(self, track_ids: list[str]) -> list[bool]:
        """Check if tracks are saved."""
        data = await self._request(
            "GET",
            "/me/tracks/contains",
            params={"ids": ",".join(track_ids)},
        )
        return data

    # ==================== Search ====================

    async def search(
        self,
        query: str,
        types: list[str] = ["track", "album", "artist", "playlist"],
        limit: int = 20,
        offset: int = 0,
        market: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Search Spotify.
        types: track, album, artist, playlist, show, episode
        """
        params = {
            "q": query,
            "type": ",".join(types),
            "limit": limit,
            "offset": offset,
        }
        if market:
            params["market"] = market

        return await self._request("GET", "/search", params=params)

    async def search_tracks(
        self,
        query: str,
        limit: int = 20,
    ) -> list[SpotifyTrack]:
        """Search for tracks."""
        data = await self.search(query, types=["track"], limit=limit)
        return [SpotifyTrack.from_api(t) for t in data.get("tracks", {}).get("items", [])]

    async def search_albums(
        self,
        query: str,
        limit: int = 20,
    ) -> list[SpotifyAlbum]:
        """Search for albums."""
        data = await self.search(query, types=["album"], limit=limit)
        return [SpotifyAlbum.from_api(a) for a in data.get("albums", {}).get("items", [])]

    async def search_artists(
        self,
        query: str,
        limit: int = 20,
    ) -> list[SpotifyArtist]:
        """Search for artists."""
        data = await self.search(query, types=["artist"], limit=limit)
        return [SpotifyArtist.from_api(a) for a in data.get("artists", {}).get("items", [])]

    async def search_playlists(
        self,
        query: str,
        limit: int = 20,
    ) -> list[SpotifyPlaylist]:
        """Search for playlists."""
        data = await self.search(query, types=["playlist"], limit=limit)
        return [SpotifyPlaylist.from_api(p) for p in data.get("playlists", {}).get("items", [])]

    # ==================== Top Items ====================

    async def get_top_artists(
        self,
        time_range: TimeRange = TimeRange.MEDIUM,
        limit: int = 20,
    ) -> list[SpotifyArtist]:
        """Get user's top artists."""
        data = await self._request(
            "GET",
            "/me/top/artists",
            params={"time_range": time_range.value, "limit": limit},
        )
        return [SpotifyArtist.from_api(a) for a in data.get("items", [])]

    async def get_top_tracks(
        self,
        time_range: TimeRange = TimeRange.MEDIUM,
        limit: int = 20,
    ) -> list[SpotifyTrack]:
        """Get user's top tracks."""
        data = await self._request(
            "GET",
            "/me/top/tracks",
            params={"time_range": time_range.value, "limit": limit},
        )
        return [SpotifyTrack.from_api(t) for t in data.get("items", [])]

    # ==================== Recently Played ====================

    async def get_recently_played(
        self,
        limit: int = 50,
        after: Optional[datetime] = None,
        before: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Get recently played tracks."""
        params = {"limit": limit}

        if after:
            params["after"] = int(after.timestamp() * 1000)
        if before:
            params["before"] = int(before.timestamp() * 1000)

        data = await self._request("GET", "/me/player/recently-played", params=params)
        return data.get("items", [])

    # ==================== Follow ====================

    async def follow_playlist(self, playlist_id: str, public: bool = True) -> bool:
        """Follow a playlist."""
        await self._request(
            "PUT",
            f"/playlists/{playlist_id}/followers",
            json={"public": public},
        )
        return True

    async def unfollow_playlist(self, playlist_id: str) -> bool:
        """Unfollow a playlist."""
        await self._request("DELETE", f"/playlists/{playlist_id}/followers")
        return True

    async def follow_artists(self, artist_ids: list[str]) -> bool:
        """Follow artists."""
        await self._request(
            "PUT",
            "/me/following",
            params={"type": "artist"},
            json={"ids": artist_ids},
        )
        return True

    async def unfollow_artists(self, artist_ids: list[str]) -> bool:
        """Unfollow artists."""
        await self._request(
            "DELETE",
            "/me/following",
            params={"type": "artist"},
            json={"ids": artist_ids},
        )
        return True

    async def close(self) -> None:
        """Close HTTP client."""
        await self._http_client.aclose()

    async def __aenter__(self) -> "SpotifyClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class SpotifyError(Exception):
    """Spotify API error."""
    pass
