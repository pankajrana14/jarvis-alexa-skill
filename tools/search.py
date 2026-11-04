import os
import requests

TAVILY_API_URL = "https://api.tavily.com/search"


def search_web(query: str, max_results: int = 3) -> str:
    """Search the web using Tavily API. Returns a plain-text summary."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return "Web search is not configured."

    try:
        response = requests.post(
            TAVILY_API_URL,
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                # Tavily's generated answer adds 0.5-5s; the LLM summarises the
                # raw results itself, and Alexa allows ~8s for the whole turn.
                "include_answer": False,
            },
            timeout=3,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("answer"):
            return data["answer"]

        results = data.get("results", [])
        if not results:
            return "No search results found."

        parts = []
        for r in results[:max_results]:
            title = r.get("title", "")
            snippet = r.get("content", "")[:500]
            parts.append(f"{title}: {snippet}")
        return " | ".join(parts)

    except requests.Timeout:
        return "Search timed out. Please try again."
    except Exception as e:
        return f"Search failed: {e}"
