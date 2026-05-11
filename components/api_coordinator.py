"""
APICoordinator component for managing API interactions.
Handles concurrent API calls with rate limiting and result aggregation.
"""

import threading
import time
from typing import Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..core import BaseComponent
from classes import AnimeList


class APICoordinator(BaseComponent):
    """
    Coordinates API interactions with rate limiting and concurrent processing.
    Manages search operations across multiple APIs.
    """

    def __init__(self):
        super().__init__("APICoordinator")
        self._api = None
        self._rate_limiter = RateLimiter()
        self._executor = None
        self._max_workers = 4

    def _initialize(self) -> None:
        """Initialize the API coordinator."""
        self.log("API_COORDINATOR", "Initializing API Coordinator")
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)

    def _start(self) -> None:
        """Start the API coordinator."""
        self.log("API_COORDINATOR", "Starting API Coordinator")

    def _stop(self) -> None:
        """Stop the API coordinator."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
        self.log("API_COORDINATOR", "API Coordinator stopped")

    def set_api(self, api) -> None:
        """
        Set the API instance.

        Args:
            api: The anime API instance
        """
        self._api = api

    def search_anime(self, terms: str, limit: int = 50, force_search: bool = False) -> Optional[AnimeList]:
        """
        Search for anime using APIs.

        Args:
            terms: Search terms
            limit: Maximum results per API
            force_search: Force online search

        Returns:
            AnimeList with search results or None
        """
        if not self._api:
            self.log("API_COORDINATOR", "[ERROR] - API not initialized")
            return None

        if not terms or len(terms.strip()) < 3:
            return None

        # Rate limiting check
        if not self._rate_limiter.allow_request():
            self.log("API_COORDINATOR", "Rate limit exceeded, skipping search")
            return None

        try:
            self.log("API_COORDINATOR", f"Searching '{terms}' with APIs")

            # Perform concurrent API search
            future = self._executor.submit(self._perform_api_search, terms, limit)
            results = future.result(timeout=30)  # 30 second timeout

            if results:
                self.log("API_COORDINATOR", f"Found {len(results)} results")
                return results
            else:
                self.log("API_COORDINATOR", "No results found")
                return None

        except Exception as e:
            self.log("API_COORDINATOR", f"Search failed: {e}")
            return None

    def _perform_api_search(self, terms: str, limit: int) -> Optional[AnimeList]:
        """
        Perform the actual API search.

        Args:
            terms: Search terms
            limit: Result limit

        Returns:
            AnimeList or None
        """
        try:
            search_results = self._api.searchAnime(terms, limit=limit)

            # Deduplicate results
            if search_results:
                search_results = self._deduplicate_results(search_results)

            return search_results

        except Exception as e:
            self.log("API_COORDINATOR", f"API search error: {e}")
            return None

    def _deduplicate_results(self, results: AnimeList) -> AnimeList:
        """
        Remove duplicate results based on anime ID.

        Args:
            results: Search results

        Returns:
            Deduplicated AnimeList
        """
        seen_ids = set()
        deduplicated = []

        for anime in results:
            if anime.id and anime.id not in seen_ids:
                seen_ids.add(anime.id)
                deduplicated.append(anime)

        return AnimeList(deduplicated)

    def get_broadcast_schedule(self) -> Optional[Any]:
        """
        Get broadcast schedule from API.

        Returns:
            Broadcast data or None
        """
        if not self._api:
            return None

        try:
            return self._api.getBroadcast()
        except Exception as e:
            self.log("API_COORDINATOR", f"Failed to get broadcast schedule: {e}")
            return None

    def cancel_search(self) -> None:
        """Cancel any ongoing search operations."""
        # This is a simplified implementation
        # In a real implementation, you'd need to track futures and cancel them
        self.log("API_COORDINATOR", "Search cancellation requested")


class RateLimiter:
    """
    Simple rate limiter for API requests.
    """

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests = []
        self.lock = threading.Lock()

    def allow_request(self) -> bool:
        """
        Check if a request is allowed under rate limits.

        Returns:
            True if request is allowed, False otherwise
        """
        with self.lock:
            now = time.time()
            # Remove old requests outside the time window
            self.requests = [req for req in self.requests if now - req < 60]

            if len(self.requests) < self.requests_per_minute:
                self.requests.append(now)
                return True
            else:
                return False