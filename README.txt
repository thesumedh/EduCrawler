IIT WEB CRAWLER
-----------------------------------------------

WHAT IT DOES
- Crawls 10 IIT websites, one institution at a time or all 10 sequentially.
- Shows five stages: robots.txt, politeness, crawl, permissions, and summary.
- Reads robots.txt before crawling.
- Checks Allow/Disallow rules and skips blocked paths.
- Uses a minimum 2-second delay between page requests (or a longer Crawl-delay declared in robots.txt).
- Stops instead of guessing when robots.txt permissions cannot be confirmed due to a network/server error or an HTML response.
- Treats HTTP 401/403 for robots.txt as forbidden and stops.
- Extracts page title, headings, description, word count, links, emails, and possible phone numbers.
- Saves results to crawl_results.json and exposes a readable JSON endpoint at http://localhost:8000/results.

REQUIREMENTS
- Python 3.9 or newer recommended.
- No third-party packages required; uses Python standard library only.
- Internet connection required for crawling external IIT websites.

HOW TO RUN (Windows)
1. Extract the ZIP file to a normal folder.
2. Open the folder.
3. Click the folder address bar, type cmd, and press Enter.
4. Run: python app.py
   If that command is not recognised, try: py app.py
5. Open http://localhost:8000 in your browser if it does not open automatically.
6. Click "Crawl this IIT" for one site, or "Crawl all 10 IITs".
7. After a crawl, use "View saved JSON results" or open crawl_results.json in VS Code.

IMPORTANT
- A crawl may take time because the tool waits politely between page requests.
- The crawler is intentionally limited to 4 HTML pages per IIT.
- Some sites may block automated requests, redirect to a different hostname, or return a non-HTML page. Such a site may produce few/no results; this does not necessarily mean the code is broken.
- robots.txt is a crawler preference/permission mechanism, not authentication. This student tool only fetches public pages and follows the site's published rules as implemented here.
- Stop the server with Ctrl+C in the terminal.
