# -*- coding: utf-8 -*-
"""
Web Search Tool for PPTX Pro Skill
Provides web search and image search capabilities using Tencent Search API.

Usage:
    python web_search.py --query "AI trends 2024" --type text --count 10
    python web_search.py --query "technology background" --type image --count 10

Limits:
    - Text search: max 3 queries per session
    - Image search: max 3 queries per session
"""

import argparse
import json
import sys
import os
from typing import Dict, Any, Optional

# Try to import from utils/config.py, fallback to defaults
try:
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'metierial', 'utils', 'config.py')
    if os.path.exists(config_path):
        sys.path.insert(0, os.path.dirname(config_path))
        from config import TENCENT_ID, TENCENT_KEY, TENCENT_ENDPOINT, TENCENT_IMG_ENDPOINT
    else:
        raise ImportError("Config not found")
except ImportError:
    # Default API configuration
    TENCENT_ID = "TENCENT_SECRET_ID_PLACEHOLDER"
    TENCENT_KEY = "TENCENT_SECRET_KEY_PLACEHOLDER"
    TENCENT_ENDPOINT = "wsa.tencentcloudapi.com"
    TENCENT_IMG_ENDPOINT = "wimgs.tencentcloudapi.com"


class TencentSearchTool:
    """Tencent Search API wrapper"""

    def __init__(self, endpoint: str = TENCENT_ENDPOINT, service: str = "wsa", version: str = "2025-05-08"):
        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.common.common_client import CommonClient

            self.cred = credential.Credential(TENCENT_ID, TENCENT_KEY)
            httpProfile = HttpProfile()
            httpProfile.endpoint = endpoint
            clientProfile = ClientProfile()
            clientProfile.httpProfile = httpProfile
            self.client = CommonClient(service, version, self.cred, "", profile=clientProfile)
            self.available = True
        except ImportError:
            print("Warning: tencentcloud-sdk-python not installed. Search functionality disabled.")
            print("Install with: pip install tencentcloud-sdk-python")
            self.available = False

    def search(self, query: str, action: str = "SearchPro", params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.available:
            return {"error": "Tencent SDK not available"}

        if params is None:
            params = {"Query": query}

        try:
            resp = self.client.call_json(action, params)
            return resp
        except Exception as e:
            return {"error": str(e)}


# Session limits and cache
_search_cache = set()
_search_count = 0
_image_search_count = 0


def web_search(query: str, count: int = 10) -> str:
    """
    Search the web using Tencent Search API.
    Returns passage results.

    Limits: 3 searches per session.
    """
    global _search_cache, _search_count

    if _search_count >= 3:
        return "Warning: Reached search limit (3). Please use existing information."

    if query in _search_cache:
        return "Warning: This query was already executed. Avoid duplicate searches."

    _search_cache.add(query)
    _search_count += 1

    try:
        print(f"  Searching for: '{query}'...", end="", flush=True)
        searcher = TencentSearchTool(endpoint=TENCENT_ENDPOINT, service="wsa", version="2025-05-08")

        params = {"Query": query, "Mode": 0}
        if count in [10, 20, 30, 40, 50]:
            params["Cnt"] = count

        result = searcher.search(query, action="SearchPro", params=params)

        if "error" in result:
            print(f" FAILED: {result['error']}")
            return f"Search failed: {result['error']}"

        pages = result.get("Response", {}).get("Pages", [])
        formatted_results = []
        for page_str in pages:
            try:
                page = json.loads(page_str)
                title = page.get("title", "No title")
                url = page.get("url", "No URL")
                passage = page.get("passage", "")
                formatted_results.append(f"Title: {title}\nURL: {url}\nSummary: {passage}\n---")
            except:
                continue

        res_str = "\n".join(formatted_results) if formatted_results else "No results found."
        print(f" Found {len(formatted_results)} results.")
        return res_str
    except Exception as e:
        print(f" Exception: {e}")
        return f"Search exception: {str(e)}"


def image_search(query: str, count: int = 10) -> str:
    """
    Search for images using Tencent Image Search API.
    Returns image URLs and descriptions.

    Limits: 3 image searches per session.
    """
    global _image_search_count

    if _image_search_count >= 3:
        return "Warning: Reached image search limit (3). Use found images."

    _image_search_count += 1

    try:
        print(f"  Searching images for: '{query}'...", end="", flush=True)
        searcher = TencentSearchTool(endpoint=TENCENT_ENDPOINT, service="wsa", version="2025-05-08")

        # Mode=2 includes image results
        params = {"Query": query, "Mode": 2, "Cnt": 10}
        result = searcher.search(query, action="SearchPro", params=params)

        # Fallback to wimgs endpoint if needed
        if "error" in result:
            searcher_fallback = TencentSearchTool(endpoint=TENCENT_IMG_ENDPOINT, service="wimgs", version="2022-08-18")
            result = searcher_fallback.search(query, action="SearchImage", params={"Query": query})

            if "error" in result and "InvalidAction" in result["error"]:
                result = searcher_fallback.search(query, action="SearchPro", params={"Query": query})

        if "error" in result:
            print(f" FAILED: {result['error']}")
            return f"Image search failed: {result['error']}"

        pages = result.get("Response", {}).get("Pages", [])
        image_results = []
        for page_str in pages:
            try:
                page = json.loads(page_str)
                imgs = page.get("images", [])
                title = page.get("title", "Related image")
                for img_url in imgs:
                    image_results.append(f"Description: {title}\nURL: {img_url}")
            except:
                continue

        res_str = "\n".join(image_results[:count]) if image_results else "No images found."
        print(f" Found {len(image_results)} images.")
        return res_str
    except Exception as e:
        print(f" Exception: {e}")
        return f"Image search exception: {str(e)}"


def main():
    parser = argparse.ArgumentParser(description="Web Search Tool for PPTX Pro")
    parser.add_argument("--query", "-q", required=True, help="Search query")
    parser.add_argument("--type", "-t", choices=["text", "image"], default="text", help="Search type")
    parser.add_argument("--count", "-c", type=int, default=10, help="Number of results")
    parser.add_argument("--output", "-o", help="Output file for results")

    args = parser.parse_args()

    if args.type == "text":
        result = web_search(args.query, args.count)
    else:
        result = image_search(args.query, args.count)

    print(f"\n{result}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
