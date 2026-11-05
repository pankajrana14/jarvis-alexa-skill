import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from unittest.mock import patch, MagicMock


def _mock_response(answer=None, results=None):
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"answer": answer, "results": results or []}
    return mock


def test_search_web_returns_answer_field_when_present():
    from tools.search import search_web
    with patch("tools.search.requests.post", return_value=_mock_response(answer="Paris is the capital of France.")):
        result = search_web("capital of France")
    assert result == "Paris is the capital of France."


def test_search_web_returns_result_snippets_when_no_answer():
    from tools.search import search_web
    results = [{"title": "France Info", "content": "France is a country in Western Europe with a rich history."}]
    with patch("tools.search.requests.post", return_value=_mock_response(results=results)):
        result = search_web("France")
    assert "France" in result


def test_search_web_handles_timeout_gracefully():
    from tools.search import search_web
    with patch("tools.search.requests.post", side_effect=requests.Timeout):
        result = search_web("anything")
    assert "timed out" in result.lower()


def test_search_web_returns_not_configured_without_api_key():
    from tools.search import search_web
    with patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
        result = search_web("test query")
    assert "not configured" in result.lower()


def test_search_web_returns_no_results_message_on_empty_results():
    from tools.search import search_web
    with patch("tools.search.requests.post", return_value=_mock_response(results=[])):
        result = search_web("obscure query xyz")
    assert "No search results" in result


def test_search_web_keeps_up_to_500_chars_per_snippet():
    from tools.search import search_web
    results = [{"title": "T", "content": "x" * 800}]
    with patch("tools.search.requests.post", return_value=_mock_response(results=results)):
        result = search_web("anything")
    assert result.count("x") == 500
