from fastmcp import FastMCP
from datetime import datetime
import requests
import os
import random
import functools
import time

mcp = FastMCP("th0rn0")

@mcp.tool
def greet(name: str) -> str:
    """Returns a greeting message."""
    return f"Heyup, {name}!"


@mcp.tool
def get_time() -> str:
    """
    Returns the current server time as a string.
    """
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

# --- Simple TTL cache decorator ---
def ttl_cache(ttl_seconds: int = 600, maxsize: int = 128):
    def decorator(func):
        cached_func = functools.lru_cache(maxsize=maxsize)(func)
        timestamps = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = args + tuple(sorted(kwargs.items()))
            now = time.time()
            if key in timestamps and now - timestamps[key] > ttl_seconds:
                # Expired, clear cache for this key
                cached_func.cache_clear()
                timestamps[key] = now
            else:
                timestamps.setdefault(key, now)
            return cached_func(*args, **kwargs)

        wrapper.cache_info = cached_func.cache_info
        wrapper.cache_clear = cached_func.cache_clear
        return wrapper
    return decorator

# --- Cached web_search function ---
@ttl_cache(ttl_seconds=600)  # cache for 10 minutes
def _fetch_web_search(query: str, num_results: int = 20):
    google_results = []
    duck_results = []

    # --- Google Custom Search ---
    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id = os.environ.get("GOOGLE_CSE_ID")
    if api_key and cse_id:
        remaining = min(num_results, 100)
        start = 1
        while remaining > 0:
            count = min(remaining, 10)
            params = {
                "key": api_key,
                "cx": cse_id,
                "q": query,
                "num": count,
                "start": start
            }
            try:
                response = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=5)
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])
                for item in items:
                    google_results.append({"title": item.get("title"), "url": item.get("link")})
                remaining -= len(items)
                start += len(items)
                if not items:
                    break
            except Exception as e:
                google_results.append({"title": f"Google API failed: {e}", "url": None})
                break

    # --- DuckDuckGo ---
    try:
        search_url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_redirect": 1,
            "skip_disambig": 1
        }
        response = requests.get(search_url, params=params, timeout=5)
        response.raise_for_status()
        related_topics = response.json().get("RelatedTopics", [])
        for topic in related_topics:
            if "Text" in topic and "FirstURL" in topic:
                duck_results.append({"title": topic["Text"], "url": topic["FirstURL"]})
            elif "Topics" in topic:
                subtopic = topic["Topics"][0]
                duck_results.append({"title": subtopic["Text"], "url": subtopic["FirstURL"]})
    except Exception as e:
        duck_results.append({"title": f"DuckDuckGo API failed: {e}", "url": None})

    # --- Weighted interleaving ---
    weighted_results = []
    g_index, d_index = 0, 0
    total_weight = 0.7 + 0.3
    g_prob = 0.7 / total_weight
    d_prob = 0.3 / total_weight

    while len(weighted_results) < num_results and (g_index < len(google_results) or d_index < len(duck_results)):
        r = random.random()
        if r < g_prob and g_index < len(google_results):
            weighted_results.append(google_results[g_index])
            g_index += 1
        elif d_index < len(duck_results):
            weighted_results.append(duck_results[d_index])
            d_index += 1
        elif g_index < len(google_results):
            weighted_results.append(google_results[g_index])
            g_index += 1
        else:
            break

    # --- Deduplicate by URL ---
    seen_urls = set()
    deduped_results = []
    for r in weighted_results:
        url = r.get("url")
        if url and url not in seen_urls:
            deduped_results.append({"title": r["title"], "url": url})
            seen_urls.add(url)

    return deduped_results[:num_results]

# --- MCP tool wrapper ---
@mcp.tool
def web_search(query: str, num_results: int = 20) -> list:
    return _fetch_web_search(query, num_results)

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8080)