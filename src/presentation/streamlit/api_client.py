"""Shared HTTP helpers for Streamlit pages talking to the FastAPI backend."""

import requests

API_BASE_URL = "http://localhost:8000/api"
API_TIMEOUT = 30


def api_get(path: str, **kwargs) -> requests.Response | None:
    """Send a GET request to the API. Returns None on connection error."""
    try:
        return requests.get(f"{API_BASE_URL}{path}", timeout=API_TIMEOUT, **kwargs)
    except requests.ConnectionError:
        return None


def api_post(path: str, **kwargs) -> requests.Response | None:
    """Send a POST request to the API. Returns None on connection error."""
    try:
        return requests.post(f"{API_BASE_URL}{path}", timeout=API_TIMEOUT, **kwargs)
    except requests.ConnectionError:
        return None


def api_delete(path: str, **kwargs) -> requests.Response | None:
    """Send a DELETE request to the API. Returns None on connection error."""
    try:
        return requests.delete(f"{API_BASE_URL}{path}", timeout=API_TIMEOUT, **kwargs)
    except requests.ConnectionError:
        return None
