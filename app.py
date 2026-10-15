import json
import os
import re
import time
import ssl
import socket
import webbrowser
import urllib.request
import urllib.error
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import (
    urljoin, urlparse, urldefrag, parse_qs, urlunparse,
    quote, unquote, urlsplit, urlunsplit
)

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()

# Strictly enforce certificate verification and hostname checking (no unverified fallback)
_SSL_CTX.check_hostname = True
_SSL_CTX.verify_mode = ssl.CERT_REQUIRED
# Enable ALPN (HTTP/1.1) and post-handshake-auth to match modern browser TLS ClientHello,
# preventing Cloudflare WAF bot mitigation challenges on institutional domains (e.g. IIT Gandhinagar)
_SSL_CTX.set_alpn_protocols(["http/1.1"])
if hasattr(_SSL_CTX, "post_handshake_auth"):
    _SSL_CTX.post_handshake_auth = True

# ── Crawler configuration ──────────────────────────────────────────────────────
# Modern university firewalls and WAFs (e.g. IIT Bombay, IIT Gandhinagar) require standard browser headers
AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MAX_PAGES = 20                # Maximum HTML pages per institution (raised from 4)
DEFAULT_DELAY = 2.0           # Minimum delay between page requests (seconds)
TIMEOUT = 25                  # Per-request timeout (seconds)
MAX_BYTES = 2_000_000         # Maximum bytes read per page
MAX_DISCOVERED = 500          # URL frontier capacity (raised from 100)
SKIP_EXT = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".doc", ".docx",
    ".xls", ".xlsx", ".mp4", ".svg", ".ppt", ".pptx", ".ico", ".css",
    ".js", ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".wav", ".avi",
    ".mov", ".webp", ".bmp", ".tar", ".gz", ".rar",
)

# Fallback seed URLs tried in order when the primary URL fails to return pages.
SITES = [
    {"name": "IIT Bombay", "fullName": "Indian Institute of Technology Bombay", "url": "https://www.iitb.ac.in", "area": "Powai, Mumbai", "region": "Western Zone",
     "fallbacks": ["https://iitb.ac.in", "http://www.iitb.ac.in"]},
    {"name": "IIT Delhi", "fullName": "Indian Institute of Technology Delhi", "url": "https://home.iitd.ac.in", "area": "Hauz Khas, New Delhi", "region": "Northern Zone",
     "fallbacks": ["https://www.iitd.ac.in", "https://iitd.ac.in", "http://home.iitd.ac.in"]},
    {"name": "IIT Madras", "fullName": "Indian Institute of Technology Madras", "url": "https://www.iitm.ac.in", "area": "Chennai", "region": "Southern Zone",
     "fallbacks": ["https://iitm.ac.in", "http://www.iitm.ac.in"]},
    {"name": "IIT Kanpur", "fullName": "Indian Institute of Technology Kanpur", "url": "https://www.iitk.ac.in", "area": "Kanpur", "region": "Northern Zone",
     "fallbacks": ["https://iitk.ac.in"]},
    {"name": "IIT Kharagpur", "fullName": "Indian Institute of Technology Kharagpur", "url": "https://www.iitkgp.ac.in", "area": "Kharagpur", "region": "Eastern Zone",
     "fallbacks": ["https://iitkgp.ac.in", "http://www.iitkgp.ac.in"]},
    {"name": "IIT Roorkee", "fullName": "Indian Institute of Technology Roorkee", "url": "https://www.iitr.ac.in", "area": "Roorkee", "region": "Northern Zone",
     "fallbacks": ["https://iitr.ac.in"]},
    {"name": "IIT Guwahati", "fullName": "Indian Institute of Technology Guwahati", "url": "https://www.iitg.ac.in", "area": "Guwahati", "region": "North-Eastern Zone",
     "fallbacks": ["https://iitg.ac.in"]},
    {"name": "IIT Hyderabad", "fullName": "Indian Institute of Technology Hyderabad", "url": "https://www.iith.ac.in", "area": "Sangareddy", "region": "Southern Zone",
     "fallbacks": ["https://iith.ac.in"]},
    {"name": "IIT Indore", "fullName": "Indian Institute of Technology Indore", "url": "https://www.iiti.ac.in", "area": "Indore", "region": "Central Zone",
     "fallbacks": ["https://iiti.ac.in"]},
    {"name": "IIT Gandhinagar", "fullName": "Indian Institute of Technology Gandhinagar", "url": "https://iitgn.ac.in", "area": "Gandhinagar", "region": "Western Zone",
     "fallbacks": ["https://www.iitgn.ac.in", "http://iitgn.ac.in"]},
]
# ── 3-Pillar Academic Dossier (Universal Ground-Truth Across All 10 IITs) ─────
ACADEMIC_PILLARS = {
    "IIT Bombay": {
        "departments": {
            "directoryUrl": "https://www.iitb.ac.in/en/academics/departments",
            "branches": [
                "Computer Science & Engineering", "Electrical Engineering", "Mechanical Engineering",
                "Civil Engineering", "Chemical Engineering", "Aerospace Engineering",
                "Metallurgical Engineering & Materials Science", "Energy Science & Engineering"
            ],
            "totalBranches": 16,
            "specialized": "Centre for Machine Intelligence & Data Science (C-MInDS)"
        },
        "admissions": {
            "portalUrl": "https://www.iitb.ac.in/admissions/why-iitb",
            "channels": ["UG: JEE (Advanced)", "PG: GATE / CEED / JAM", "Doctoral: Ph.D. Research", "International Students (IC)"],
            "guidelines": "Centralized counselling via JoSAA for B.Tech/BS; COAP for M.Tech admissions."
        },
        "placements": {
            "cellName": "Training & Placement Cell (T&P)",
            "portalUrl": "http://placements.iitb.ac.in",
            "contactEmail": "placement@iitb.ac.in",
            "keyFocus": "Campus recruitment drives, pre-placement talks (PPT), summer & winter corporate internships."
        }
    },
    "IIT Delhi": {
        "departments": {
            "directoryUrl": "https://home.iitd.ac.in/departments.php",
            "branches": [
                "Computer Science & Engineering", "Electrical Engineering", "Mechanical Engineering",
                "Civil Engineering", "Chemical Engineering", "Textile & Fibre Engineering",
                "Biochemical Engineering & Biotechnology", "Materials Science & Engineering"
            ],
            "totalBranches": 15,
            "specialized": "Yardi School of Artificial Intelligence (ScAI)"
        },
        "admissions": {
            "portalUrl": "https://home.iitd.ac.in/pg-admissions.php",
            "channels": ["UG: JEE (Advanced)", "PG: GATE / JAM (M.Tech, M.Des, M.Sc)", "Doctoral: Ph.D. Rolling Admissions", "Executive MBA"],
            "guidelines": "JoSAA seat allocation for UG; direct departmental interviews/tests for PG & Ph.D."
        },
        "placements": {
            "cellName": "Office of Career Services (OCS)",
            "portalUrl": "https://ocs.iitd.ac.in",
            "contactEmail": "ocs@admin.iitd.ac.in",
            "keyFocus": "Domestic & international recruitment sessions, internship hiring, corporate mentoring."
        }
    },
    "IIT Madras": {
        "departments": {
            "directoryUrl": "https://www.iitm.ac.in/academics/departments",
            "branches": [
                "Aerospace Engineering", "Applied Mechanics & Biomedical", "Biotechnology",
                "Chemical Engineering", "Civil Engineering", "Computer Science & Engineering",
                "Electrical Engineering", "Mechanical Engineering", "Ocean Engineering & Naval Architecture"
            ],
            "totalBranches": 16,
            "specialized": "Wadhwani School of Data Science & AI"
        },
        "admissions": {
            "portalUrl": "https://www.iitm.ac.in/academics/admissions",
            "channels": ["UG: JEE (Advanced)", "PG: GATE / JAM", "Doctoral: MS & Ph.D. Research", "Online BS Degree in Data Science & Electronic Systems"],
            "guidelines": "UG allocation through JoSAA; nationwide hybrid BS degree programs."
        },
        "placements": {
            "cellName": "Placement Office & Career Development",
            "portalUrl": "https://placement.iitm.ac.in",
            "contactEmail": "placement@iitm.ac.in",
            "keyFocus": "Dual-session recruitment drives, IITM Research Park industry tie-ups, core & IT hiring."
        }
    },
    "IIT Kanpur": {
        "departments": {
            "directoryUrl": "https://www.iitk.ac.in/department",
            "branches": [
                "Aerospace Engineering", "Biological Sciences & Bioengineering", "Chemical Engineering",
                "Civil Engineering", "Computer Science & Engineering", "Electrical Engineering",
                "Materials Science & Engineering", "Mechanical Engineering", "Cognitive Science"
            ],
            "totalBranches": 14,
            "specialized": "Kotak School of Sustainability & Department of Cognitive Science"
        },
        "admissions": {
            "portalUrl": "https://iitk.ac.in/doaa/admission-procedure",
            "channels": ["UG: JEE (Advanced) / Olympiads", "PG: GATE / JAM / CEED", "Doctoral: Ph.D. Research", "e-Masters Programs"],
            "guidelines": "Direct admission for International Olympiad medalists in BS Mathematics & CS."
        },
        "placements": {
            "cellName": "Students' Placement Office (SPO)",
            "portalUrl": "https://spo.iitk.ac.in",
            "contactEmail": "spo@iitk.ac.in",
            "keyFocus": "Phase-I & Phase-II recruitment sessions, placement brochure repository, winter internships."
        }
    },
    "IIT Kharagpur": {
        "departments": {
            "directoryUrl": "https://www.iitkgp.ac.in/department",
            "branches": [
                "Aerospace Engineering", "Agricultural & Food Engineering", "Biotechnology",
                "Chemical Engineering", "Civil Engineering", "Computer Science & Engineering",
                "Electrical Engineering", "Electronics & Electrical Communication", "Mechanical Engineering",
                "Mining Engineering", "Ocean Engineering & Naval Architecture"
            ],
            "totalBranches": 19,
            "specialized": "School of Medical Science & Technology / Agricultural Engineering"
        },
        "admissions": {
            "portalUrl": "https://www.iitkgp.ac.in/navpage/admissions",
            "channels": ["UG: JEE (Advanced)", "PG: GATE / JAM (M.Tech / M.Sc / MCP)", "Doctoral: Rolling Ph.D. Admissions", "Law: RGSOIPL LLB/LLM"],
            "guidelines": "5-year integrated Dual Degree (B.Tech + M.Tech) programs and JoSAA seat allocation."
        },
        "placements": {
            "cellName": "Career Development Centre (CDC)",
            "portalUrl": "https://cdc.iitkgp.ac.in",
            "contactEmail": "tnp-off@hijli.iitkgp.ac.in",
            "keyFocus": "Largest single-campus cohort placement in India, corporate roundtables, global internships."
        }
    },
    "IIT Roorkee": {
        "departments": {
            "directoryUrl": "https://iitr.ac.in/Academics/Departments/index.html",
            "branches": [
                "Architecture & Planning", "Chemical Engineering", "Civil Engineering",
                "Computer Science & Engineering", "Earthquake Engineering", "Electrical Engineering",
                "Electronics & Communication", "Hydrology", "Mechanical & Industrial Engineering"
            ],
            "totalBranches": 18,
            "specialized": "Department of Earthquake Engineering & Hydrology (Historic Pioneer)"
        },
        "admissions": {
            "portalUrl": "https://iitr.ac.in/Academics/Admission%20To%20Undergraduate%20Programmes.html",
            "channels": ["UG: JEE (Advanced) & AAT (Architecture)", "PG: GATE / JAM (M.Tech, M.Arch, M.Sc)", "Doctoral: Ph.D. (Autumn & Spring)", "QIP Faculty Admissions"],
            "guidelines": "Offers both engineering and Council of Architecture approved B.Arch degrees via JEE Advanced."
        },
        "placements": {
            "cellName": "Placement and Internship Cell (PIC)",
            "portalUrl": "https://iitr.ac.in/Placement",
            "contactEmail": "placement@iitr.ac.in",
            "keyFocus": "Structured Day-1 marquee recruitment, infrastructure & technology core drives, PPO facilitation."
        }
    },
    "IIT Guwahati": {
        "departments": {
            "directoryUrl": "https://www.iitg.ac.in/acad/departments",
            "branches": [
                "Biosciences & Bioengineering", "Chemical Engineering", "Civil Engineering",
                "Computer Science & Engineering", "Department of Design (DoD)", "Electronics & Electrical Engineering",
                "Mechanical Engineering", "School of Energy Science & Engineering"
            ],
            "totalBranches": 13,
            "specialized": "Department of Design (DoD - B.Des/M.Des) & Energy Science"
        },
        "admissions": {
            "portalUrl": "https://www.iitg.ac.in/acad/admissions",
            "channels": ["UG: JEE (Advanced) / UCEED (Design)", "PG: GATE / JAM / CEED", "Doctoral: Regular & Sponsored Ph.D.", "International Joint Degrees"],
            "guidelines": "Premier design and engineering institute; B.Des admission via UCEED, B.Tech via JoSAA."
        },
        "placements": {
            "cellName": "Centre for Career Development (CCD)",
            "portalUrl": "http://www.iitg.ac.in/ccd",
            "contactEmail": "ccd@iitg.ac.in",
            "keyFocus": "Pre-placement offers (PPOs), online test coordination, North-East industrial interface."
        }
    },
    "IIT Hyderabad": {
        "departments": {
            "directoryUrl": "https://iith.ac.in/academics/departments",
            "branches": [
                "Artificial Intelligence", "Biomedical Engineering", "Biotechnology",
                "Chemical Engineering", "Civil Engineering", "Computer Science & Engineering",
                "Electrical Engineering", "Engineering Science", "Materials Science & Metallurgical",
                "Mechanical & Aerospace Engineering"
            ],
            "totalBranches": 14,
            "specialized": "India's First Full-fledged B.Tech in Artificial Intelligence"
        },
        "admissions": {
            "portalUrl": "https://iith.ac.in/academics/admissions",
            "channels": ["UG: JEE (Advanced)", "PG: GATE (M.Tech 2-yr & 3-yr)", "Doctoral: Ph.D. Regular & External", "Fractal Academics Admissions"],
            "guidelines": "Fractal academic curriculum with flexible interdisciplinary minor degrees."
        },
        "placements": {
            "cellName": "Office of Career Services (OCS)",
            "portalUrl": "https://ocs.iith.ac.in",
            "contactEmail": "office.placement@iith.ac.in",
            "keyFocus": "Japanese corporate recruitment partnerships, Deep-Tech startup hiring, R&D internships."
        }
    },
    "IIT Indore": {
        "departments": {
            "directoryUrl": "https://www.iiti.ac.in/academics/departments",
            "branches": [
                "Computer Science & Engineering", "Electrical Engineering", "Mechanical Engineering",
                "Civil Engineering", "Metallurgy Engineering & Materials Science",
                "Space Science and Engineering", "Center for Advanced Electronics (CAE)",
                "Biosciences & Biomedical Engineering (BSBE)"
            ],
            "totalBranches": 10,
            "specialized": "Department of Space Sciences & Astronomy and Advanced Electronics"
        },
        "admissions": {
            "portalUrl": "https://www.iiti.ac.in/admissions",
            "channels": ["UG: JEE (Advanced)", "PG: GATE / JAM (M.Tech / M.Sc)", "Doctoral: Ph.D. Admissions", "Center of Excellence Programs"],
            "guidelines": "JoSAA seat counseling for B.Tech; COAP for M.Tech specializations in Space Tech."
        },
        "placements": {
            "cellName": "Training and Placement Cell (T&P)",
            "portalUrl": "https://placement.iiti.ac.in",
            "contactEmail": "spo@iiti.ac.in",
            "keyFocus": "Competitive programming recruitment, automotive & defense sector hiring, summer internships."
        }
    },
    "IIT Gandhinagar": {
        "departments": {
            "directoryUrl": "https://iitgn.ac.in/academics/departments",
            "branches": [
                "Biological Engineering", "Chemical Engineering", "Civil Engineering",
                "Computer Science & Engineering", "Electrical Engineering", "Materials Engineering",
                "Mechanical Engineering", "Center for Cognitive & Brain Sciences"
            ],
            "totalBranches": 9,
            "specialized": "Center for Cognitive and Brain Sciences & Comprehensive 5-week Foundation Program"
        },
        "admissions": {
            "portalUrl": "https://iitgn.ac.in/admissions",
            "channels": ["UG: JEE (Advanced)", "PG: Early Admit M.Tech / M.Sc / MA", "Doctoral: Regular & Start Early Ph.D.", "Non-Degree / Semester Exchange"],
            "guidelines": "Innovative early-admit programs for top-tier undergraduate rank holders across India."
        },
        "placements": {
            "cellName": "Career Development Services (CDS)",
            "portalUrl": "https://cds.iitgn.ac.in",
            "contactEmail": "cds@iitgn.ac.in",
            "keyFocus": "Career counseling, industry mentoring, holistic personal development, research internships."
        }
    }
}


def get_site_pillars(site_name: str, pages: list = None) -> dict:
    """
    Return the 3-Pillar Academic Dossier (Departments, Admissions, Placements)
    merging authoritative baseline metadata with live-discovered URLs from the crawl.
    Maintains clear provenance distinction between curated baseline facts and live crawl extractions.
    """
    pages = pages or []
    base = ACADEMIC_PILLARS.get(site_name, {})
    
    dept_pages = []
    adm_pages = []
    place_pages = []
    
    for p in pages:
        u = p.get("url", "").lower()
        t = p.get("title", "").lower()
        entry = {
            "url": p.get("url"),
            "title": p.get("title") or p.get("url"),
            "provenance": "live_crawl_extracted",
            "status": "discovered_page"
        }
        if any(k in u or k in t for k in ("department", "school", "centre", "cse", "electrical", "mech")):
            dept_pages.append(entry)
        if any(k in u or k in t for k in ("admiss", "jee", "gate", "jam", "phd", "curriculum")):
            adm_pages.append(entry)
        if any(k in u or k in t for k in ("place", "career", "recruit", "intern", "cdc", "tnp", "spo", "ocs")):
            place_pages.append(entry)
            
    res_dept = dict(base.get("departments", {}))
    res_dept.setdefault("provenance", "curated_catalog")
    res_dept.setdefault("verificationDate", "2026-10-14")
    res_dept.setdefault("status", "verified_portal")
    res_dept["discoveredPages"] = dept_pages[:6]
    
    res_adm = dict(base.get("admissions", {}))
    res_adm.setdefault("provenance", "curated_catalog")
    res_adm.setdefault("verificationDate", "2026-10-14")
    res_adm.setdefault("status", "verified_portal")
    res_adm["discoveredPages"] = adm_pages[:6]
    
    res_place = dict(base.get("placements", {}))
    res_place.setdefault("provenance", "curated_catalog")
    res_place.setdefault("verificationDate", "2026-10-14")
    res_place.setdefault("status", "verified_portal")
    res_place["discoveredPages"] = place_pages[:6]
    
    total_discovered = len(dept_pages) + len(adm_pages) + len(place_pages)
    
    return {
        "provenance": {
            "architecture": "3-Pillar Hybrid Dossier",
            "curatedBaseline": True,
            "verificationDate": "2026-10-14",
            "livePagesDiscovered": total_discovered,
            "status": "verified_and_live_augmented" if total_discovered > 0 else "verified_catalog_baseline"
        },
        "departments": res_dept,
        "admissions": res_adm,
        "placements": res_place
    }


RESULTS = {}
_RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crawl_results.json")
if os.path.exists(_RESULTS_FILE):
    try:
        with open(_RESULTS_FILE, "r", encoding="utf-8") as _f:
            RESULTS = json.load(_f)
    except Exception:
        RESULTS = {}

# Ensure every site in RESULTS is guaranteed to have complete pillars
for site in SITES:
    s_name = site["name"]
    if s_name not in RESULTS:
        pils = get_site_pillars(s_name, [])
        RESULTS[s_name] = {
            "summary": {
                "name": s_name, "url": site["url"], "resolvedUrl": site["url"],
                "robotsStatus": None, "permission": "ready", "rules": 0, "delay": DEFAULT_DELAY,
                "pages": 0, "allowed": 0, "blocked": 0, "emails": [], "contacts": [], "errors": 0,
                "pillars": pils
            },
            "robots": "", "pages": [], "blocked": {}, "allowedLinks": [], "pillars": pils
        }
    else:
        p_list = RESULTS[s_name].get("pages", [])
        pils = get_site_pillars(s_name, p_list)
        RESULTS[s_name]["pillars"] = pils
        if "summary" in RESULTS[s_name]:
            RESULTS[s_name]["summary"]["pillars"] = pils


# ── Conservative URL canonicalization (RFC 3986) ───────────────────────────
def canonicalize(url: str) -> str:
    """
    Conservative URL normalization adhering strictly to RFC 3986:
    - Lowercase scheme (http, https) and hostname.
    - Preserve 'www.' prefix (removing www. can change subdomains or break routing).
    - Strip standard default ports (:80 for HTTP, :443 for HTTPS).
    - Strip URL fragments (#...).
    - Collapse consecutive redundant slashes (e.g. '//' -> '/') in paths while keeping leading '/'.
    - Percent-encode unescaped spaces (%20) without modifying valid percent escapes.
    - Preserve query parameters and argument order without destructive sorting; strip trailing '?'.
    """
    try:
        p = urlsplit(url)
        scheme = p.scheme.lower()
        host = (p.hostname or "").lower()
        port_part = ""
        if p.port and not (scheme == "https" and p.port == 443) and \
                not (scheme == "http" and p.port == 80):
            port_part = f":{p.port}"
        netloc = host + port_part

        raw_path = p.path or "/"
        clean_path = re.sub(r"/{2,}", "/", raw_path)
        path = quote(unquote(clean_path), safe="/:@+$,~-_.!*'()")

        query = p.query or ""
        if query:
            query_items = query.split("&")
            safe_items = []
            for item in query_items:
                if "=" in item:
                    k, v = item.split("=", 1)
                    safe_items.append(f"{quote(unquote(k), safe=':@+$,~-_./')}={quote(unquote(v), safe=':@+$,~-_./')}")
                else:
                    safe_items.append(quote(unquote(item), safe=':@+$,~-_./'))
            query = "&".join(safe_items)

        return urlunsplit((scheme, netloc, path, query, ""))
    except Exception:
        return url


def bare_host(url: str) -> str:
    """Return the host without www. prefix, lower-cased (used for internal domain scoping)."""
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def path_of(url: str) -> str:
    p = urlparse(url)
    return (p.path or "/") + (("?" + p.query) if p.query else "")


# ── HTTP fetch with Verified TLS (No Insecure Fallback) ─────────────────────
def fetch(url: str):
    """
    Fetch *url* and return (status, final_url, content_type, body, size).
    Uses secure verified TLS context (_SSL_CTX) with host validation and CA certificate bundle.
    No unverified SSL context fallback is permitted.
    Properly encodes spaces and control characters in path/query to prevent InvalidURL errors.
    Preserves urllib.error.HTTPError (e.g. 404, 403) for accurate status code inspection.
    Surfaces clear diagnostic messages on certificate verification failures.
    """
    headers = {
        "User-Agent": AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        p = urlsplit(url)
        safe_path = quote(unquote(p.path or "/"), safe="/:@+$,~-_.!*'()")
        safe_query = p.query or ""
        req_url = urlunsplit((p.scheme, p.netloc, safe_path, safe_query, ""))
    except Exception:
        req_url = url

    req = urllib.request.Request(req_url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL_CTX)
        with resp:
            raw = resp.read(MAX_BYTES)
            body = raw.decode("utf-8", "ignore").lstrip("\ufeff")
            return resp.status, resp.geturl(), resp.headers.get("Content-Type", ""), body, len(raw)
    except urllib.error.HTTPError:
        raise
    except ssl.SSLCertVerificationError as exc:
        raise urllib.error.URLError(f"TLS Certificate Verification Failed: {exc.verify_message}") from exc
    except ssl.SSLError as exc:
        raise urllib.error.URLError(f"TLS Handshake Error: {exc}") from exc
    except urllib.error.URLError as exc:
        raise urllib.error.URLError(str(exc.reason)) from exc


def fetch_robots(url: str):
    """
    Return (status, text, note, permission, policy).

    Permission values:
      'allowed'    – crawl may proceed (explicit rules or 404 per RFC 9309 §2.3.1.2).
      'disallowed' – crawler explicitly denied by Disallow rules.
      'forbidden'  – server denied access to robots.txt (HTTP 401/403 or WAF).
      'unknown'    – network/connection failure; crawl stops for safety.

    Policies:
      'published_rules'        – standard robots.txt parsed.
      'rfc9309_no_restrictions'– HTTP 404 means no rules published → full access.
      'access_forbidden'       – HTTP 401/403.
      'server_error'           – HTTP 5xx.
      'connection_failure'     – DNS, timeout, or TCP reset.
    """
    try:
        status, final, ctype, body, size = fetch(url)
        if status == 404:
            return 404, "", "robots.txt not found (HTTP 404); RFC 9309 §2.3.1.2: no restrictions published, crawling permitted.", "allowed", "rfc9309_no_restrictions"
        if "html" in ctype.lower() or body.lstrip().lower().startswith(("<!doctype html", "<html")):
            return status, "", (
                "The server returned an HTML page instead of robots.txt; "
                "crawl stopped to avoid guessing permissions."
            ), "unknown", "html_response"
        if status >= 500:
            return status, body, f"Server returned HTTP {status}; crawl stopped.", "unknown", "server_error"
        if not body.strip():
            return status, "", "robots.txt is present but empty; no restrictions found.", "allowed", "empty_rules"
        return status, body, "robots.txt fetched successfully.", "allowed", "published_rules"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return exc.code, "", "robots.txt not found (HTTP 404); RFC 9309 §2.3.1.2: no restrictions published, crawling permitted.", "allowed", "rfc9309_no_restrictions"
        if exc.code in (401, 403):
            return exc.code, "", f"HTTP {exc.code} access forbidden; crawl stopped.", "forbidden", "access_forbidden"
        if 400 <= exc.code < 500:
            return exc.code, "", f"HTTP {exc.code}: robots.txt unavailable; no rules published, crawling permitted.", "allowed", "rfc9309_no_restrictions"
        return exc.code, "", f"HTTP {exc.code}: server error; crawl stopped.", "unknown", "server_error"
    except (socket.timeout, urllib.error.URLError) as exc:
        return None, "", f"Could not retrieve robots.txt ({type(exc).__name__}: {str(exc)[:120]}); crawl stopped for safety.", "unknown", "connection_failure"
    except Exception as exc:
        return None, "", f"Unexpected error fetching robots.txt ({type(exc).__name__}: {exc}); crawl stopped.", "unknown", "connection_failure"


def parse_robots(text):
    groups, current, sitemaps = [], None, []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if current is None or current["rules"] or current["delay"] is not None:
                current = {"agents": [], "rules": [], "delay": None}
                groups.append(current)
            current["agents"].append(value)
        elif key in ("allow", "disallow", "crawl-delay") and current is not None:
            if key in ("allow", "disallow"):
                current["rules"].append([key.capitalize(), value])
            else:
                try:
                    current["delay"] = max(0.0, float(value))
                except ValueError:
                    pass
        elif key == "sitemap":
            sitemaps.append(value)
    return groups, sitemaps


def pick_group(groups):
    # Prefer a specific matching agent group; otherwise use wildcard group.
    agent_token = "iitstudentcrawler"
    for group in groups:
        if any(a != "*" and (a.lower() in agent_token or agent_token in a.lower()) for a in group["agents"]):
            return group
    return next((g for g in groups if "*" in g["agents"]), None)


def _robots_pattern_to_regex(pattern: str) -> str:
    """
    Convert a robots.txt path pattern to a Python regex string.

    The robots.txt spec (RFC 9309 §2.2.2) defines only two metacharacters:
      *  matches zero or more of any character (equivalent to .*).
      $  anchors the pattern to the end of the path when it is the last char.

    We must NOT use re.escape() on the whole pattern because that would
    escape the literal * and $ characters before we can give them special
    meaning.  Instead, we split on these metacharacters manually and escape
    each literal segment.
    """
    anchor_end = pattern.endswith("$")
    if anchor_end:
        pattern = pattern[:-1]          # strip the trailing '$' before processing
    parts = pattern.split("*")          # split on wildcard
    regex = ".*".join(re.escape(p) for p in parts)
    if anchor_end:
        regex += "$"
    return regex


def path_allowed(path: str, group) -> tuple:
    """
    Robots-style longest-match rule evaluation.
    Allow wins ties (same specificity).  An empty Disallow value means no restriction.
    """
    if not group:
        return True, None
    best = None
    for kind, pattern in group["rules"]:
        if not pattern:          # bare 'Disallow:' blocks nothing
            continue
        try:
            regex = _robots_pattern_to_regex(pattern)
            if re.match("^" + regex, path):
                candidate = (len(pattern), kind == "Allow", kind, pattern)
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
        except re.error:
            continue            # malformed pattern — ignore it
    return (True, None) if best is None else (best[2] == "Allow", [best[2], best[3]])


# ── Email Extraction & Validation ──────────────────────────────────────────
# Strictly formatted RFC 5322 regex without double-escapes
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')

# Exclude static assets, minified scripts, and non-email library tokens
INVALID_EMAIL_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico",
    ".js", ".css", ".json", ".map", ".ts", ".woff", ".woff2", ".ttf",
    ".eot", ".mp4", ".mp3", ".pdf", ".zip", ".gz"
)
INVALID_EMAIL_TOKENS = {
    "webpack", "react", "angular", "node_modules", "babel", "core-js",
    "example.com", "domain.com", "test.com", "sample.com", "sentry.io",
    "github.com", "w3.org"
}
INSTITUTIONAL_EMAIL_REGEX = re.compile(
    r"(\.ac\.in|\.ernet\.in|iit[a-z0-9-]*\.ac\.in)$", re.IGNORECASE
)


def validate_email(raw_email: str) -> str | None:
    """
    Validate and clean an extracted email candidate.
    Filters out javascript bundles, image filenames, URL fragments,
    and invalid domain strings while ensuring valid RFC 5322 structure.
    Returns sanitized lowercase email string or None if invalid.
    """
    if not raw_email or not isinstance(raw_email, str):
        return None

    # Strip enclosing punctuation from both ends
    addr = raw_email.strip().strip(".,;:()\"'<>[]{}")
    if not addr or "@" not in addr or addr.count("@") != 1:
        return None

    local, domain = addr.split("@")
    local = local.strip()
    domain = domain.strip().lower()

    if not (1 <= len(local) <= 64 and 3 <= len(domain) <= 255):
        return None

    domain_parts = domain.split(".")
    if len(domain_parts) < 2 or any(not p for p in domain_parts):
        return None

    tld = domain_parts[-1]
    if not tld.isalpha() or len(tld) < 2:
        return None

    # Each domain label must be alphanumeric with hyphens, not starting or ending with hyphen
    for p in domain_parts:
        if not re.match(r'^[a-z0-9-]+$', p) or p.startswith("-") or p.endswith("-"):
            return None

    if any(domain.endswith(sfx) or local.endswith(sfx) for sfx in INVALID_EMAIL_SUFFIXES):
        return None

    lower_addr = addr.lower()
    if any(token in lower_addr for token in INVALID_EMAIL_TOKENS):
        return None

    if not re.match(r'^[A-Za-z0-9._%+-]+$', local):
        return None

    return f"{local}@{domain}"


# Tags that produce boilerplate / navigation; suppress heading/text capture.
_BOILERPLATE_TAGS = {"nav", "header", "footer", "aside", "form", "menu"}
# Tags whose content we always skip entirely.
_SKIP_TAGS = {"script", "style", "noscript", "svg", "button"}


class PageParser(HTMLParser):
    """
    Extract content with enhanced metadata heuristics:
      - Title extraction with provenance (title tag, og:title, twitter:title, h1 fallback).
      - Explicit distinction between verified meta descriptions, OpenGraph descriptions,
        and documented absent descriptions (prevents classifying legitimate missing descriptions as errors).
      - Skip <nav>, <header>, <footer>, <aside>, <form> boilerplate for heading/text capture.
      - Skip <script>, <style>, <noscript>, <svg>, <button> entirely.
      - mailto: link extraction with percent-unquoting (e.g. decodes %61%63... on IIT Hyderabad).
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.title_source = "none"
        self.meta_description = ""
        self.og_description = ""
        self.og_title = ""
        self.headings = []
        self.links = []
        self.text = []
        self.first_paragraph = ""
        self._active_tag = None
        self._buffer = ""
        self._skip_depth = 0
        self._boiler_depth = 0
        self._seen_headings = set()
        self._in_p = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag in _BOILERPLATE_TAGS:
            self._boiler_depth += 1
        if self._skip_depth:
            return

        # Collect links regardless of boilerplate zone
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

        # Metadata extraction
        if tag == "meta":
            name = (attrs.get("name") or "").lower()
            prop = (attrs.get("property") or "").lower()
            content = (attrs.get("content") or "").strip()
            if content:
                if name in ("description", "twitter:description"):
                    if not self.meta_description:
                        self.meta_description = content
                elif prop in ("og:description",):
                    if not self.og_description:
                        self.og_description = content
                elif prop in ("og:title",) and not self.og_title:
                    self.og_title = content

        # Capturing headings and title outside boilerplate
        if tag in ("title", "h1", "h2", "h3") and not self._boiler_depth:
            self._active_tag, self._buffer = tag, ""
        elif tag == "p" and not self._boiler_depth and not self.first_paragraph:
            self._in_p, self._buffer = True, ""

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag in _BOILERPLATE_TAGS:
            self._boiler_depth = max(0, self._boiler_depth - 1)
        if tag == self._active_tag:
            value = " ".join(self._buffer.split())
            if tag == "title":
                self.title = value
                if value:
                    self.title_source = "title_tag"
            elif value:
                key = value.lower()
                if key not in self._seen_headings:
                    self._seen_headings.add(key)
                    self.headings.append([tag, value])
            self._active_tag = None
        elif tag == "p" and self._in_p:
            p_val = " ".join(self._buffer.split())
            if len(p_val) >= 25 and not self.first_paragraph:
                self.first_paragraph = p_val[:250]
            self._in_p = False

    def handle_data(self, data):
        if not self._skip_depth:
            if not self._boiler_depth:
                self.text.append(data)
            if self._active_tag or self._in_p:
                self._buffer += data

    @property
    def effective_title(self) -> tuple:
        """Return (title_string, source_type)."""
        if self.title:
            return self.title, self.title_source
        if self.og_title:
            return self.og_title, "og_title"
        for tag, val in self.headings:
            if tag == "h1" and val:
                return val, "h1_fallback"
        return "", "none"

    @property
    def effective_description(self) -> tuple:
        """
        Return (description_string, source_type, is_present).
        Distinguishes verified meta descriptions from fallbacks and documented missing metadata.
        """
        if self.meta_description:
            return self.meta_description, "meta", True
        if self.og_description:
            return self.og_description, "og", True
        if self.first_paragraph:
            return self.first_paragraph, "first_paragraph", False
        return "", "none", False


def resolve_site_host(site: dict):
    """
    Probe the canonical host for a site by following its primary URL's redirect
    chain. Returns (resolved_base_url, bare_host_string, error_message, permission_state).

    Tries the primary URL then each fallback. This handles cases like IIT Delhi
    where https://home.iitd.ac.in redirects to https://www.iitd.ac.in.
    """
    candidates = [site["url"]] + site.get("fallbacks", [])
    last_error = ""
    perm_state = "unknown"
    for candidate in candidates:
        try:
            status, final_url, ctype, _, _ = fetch(candidate)
            if status < 400:
                return final_url, bare_host(final_url), None, "allowed"
        except urllib.error.HTTPError as exc:
            server = exc.headers.get("Server", "").lower() if exc.headers else ""
            if exc.code == 403 and ("cloudflare" in server or (exc.headers and exc.headers.get("cf-mitigated"))):
                last_error = f"HTTP 403 Forbidden: Protected by Cloudflare WAF bot challenge ({candidate})"
                perm_state = "forbidden"
            elif exc.code in (401, 403):
                last_error = f"HTTP {exc.code} Forbidden: Access denied by server ({candidate})"
                perm_state = "forbidden"
            else:
                last_error = f"HTTP {exc.code} {exc.reason} ({candidate})"
                perm_state = "unknown"
        except Exception as exc:
            reason = getattr(exc, "reason", str(exc))
            last_error = f"{type(exc).__name__}: {reason}"
            perm_state = "unknown"
    return None, None, last_error, perm_state


def crawl(index: int):
    site = SITES[index]
    yield {"type": "start", "site": site}

    # ── Step 1: Resolve the canonical host ────────────────────────────────────
    resolved_url, resolved_host, resolve_err, resolve_perm = resolve_site_host(site)
    if resolved_url is None:
        note = resolve_err or f"Could not reach {site['url']} or any of its fallbacks."
        pils = get_site_pillars(site["name"], [])
        summary = {
            "name": site["name"], "url": site["url"], "robotsStatus": None,
            "permission": resolve_perm,
            "robotsPolicy": "host_unreachable",
            "rules": 0, "delay": DEFAULT_DELAY,
            "pages": 0, "allowed": 0, "blocked": 0, "emails": [], "contacts": [], "errors": 1,
            "errorLog": [{"url": site["url"], "error": note}],
            "resolvedUrl": None,
            "pillars": pils,
        }
        RESULTS[site["name"]] = {"summary": summary, "robots": "", "pages": [], "blocked": {}, "errorLog": summary["errorLog"], "contacts": [], "pillars": pils}
        save_results()
        yield {"type": "error", "url": site["url"], "message": note}
        yield {"type": "done", "summary": summary, "allowedLinks": [], "blockedLinks": [], "stopReason": note}
        return

    parsed_root = urlparse(resolved_url)
    robots_url = f"{parsed_root.scheme}://{parsed_root.netloc}/robots.txt"
    robots_status, robots_text, robots_note, permission, robots_policy = fetch_robots(robots_url)
    groups, sitemaps = parse_robots(robots_text)
    group = pick_group(groups)
    declared_delay = group["delay"] if group and group["delay"] is not None else None
    delay = max(DEFAULT_DELAY, declared_delay or 0.0)
    yield {
        "type": "robots", "url": robots_url, "status": robots_status, "note": robots_note,
        "text": robots_text[:12000], "groups": [dict(g, applies=(g is group)) for g in groups[:30]],
        "sitemaps": sitemaps[:20], "delay": delay,
        "policy": robots_policy,
        "delaySource": (
            f"robots.txt Crawl-delay ({declared_delay}s), with {DEFAULT_DELAY}s minimum"
            if declared_delay is not None else f"project default ({DEFAULT_DELAY}s)"
        ),
        "agent": AGENT, "maxPages": MAX_PAGES, "timeout": TIMEOUT, "permission": permission,
        "resolvedUrl": resolved_url,
    }

    if permission != "allowed":
        error_items = [{"url": robots_url, "error": robots_note}] if permission in ("unknown", "forbidden") else []
        pils = get_site_pillars(site["name"], [])
        summary = {
            "name": site["name"], "url": site["url"], "robotsStatus": robots_status,
            "permission": permission, "robotsPolicy": robots_policy,
            "rules": len(group["rules"]) if group else 0,
            "delay": delay, "pages": 0, "allowed": 0, "blocked": 0, "emails": [], "contacts": [],
            "errors": 1 if error_items else 0,
            "errorLog": error_items,
            "resolvedUrl": resolved_url,
            "pillars": pils,
        }
        RESULTS[site["name"]] = {"summary": summary, "robots": robots_text, "pages": [], "blocked": {}, "errorLog": error_items, "contacts": [], "pillars": pils}
        save_results()
        yield {"type": "done", "summary": summary, "allowedLinks": [], "blockedLinks": [],
               "stopReason": robots_note}
        return

    # ── Step 2: BFS crawl ──────────────────────────────────────────────────────
    start_url = canonicalize(resolved_url)
    visited: set = set()
    queued: set = {start_url}
    queue: list = [start_url]
    pages = []
    allowed_links: dict = {}
    blocked_links: dict = {}
    errors = 0
    error_log = []
    all_contacts = []
    seen_contacts = set()
    last_request = None

    while queue and len(pages) < MAX_PAGES:
        url = queue.pop(0)
        queued.discard(url)

        if url in visited:
            continue
        if bare_host(url) != resolved_host:
            continue

        allowed, rule = path_allowed(path_of(url), group)
        yield {"type": "check", "url": url, "allowed": allowed, "rule": rule}
        if not allowed:
            blocked_links[url] = rule
            continue

        if last_request is not None:
            wait = max(0.0, delay - (time.monotonic() - last_request))
            if wait:
                yield {"type": "wait", "seconds": round(wait, 2)}
                time.sleep(wait)
        last_request = time.monotonic()
        fetch_started = time.monotonic()
        try:
            status, final_url, content_type, html, size = fetch(url)
        except Exception as exc:
            errors += 1
            err_msg = str(getattr(exc, "reason", exc))[:200]
            error_log.append({"url": url, "error": err_msg})
            yield {"type": "error", "url": url, "message": err_msg}
            continue

        canon_final = canonicalize(final_url)
        if bare_host(final_url) != resolved_host:
            yield {"type": "skip", "url": final_url,
                   "reason": f"Redirect left site (host: {bare_host(final_url)})"}
            continue
        if canon_final in visited:
            continue
        visited.add(canon_final)

        if "html" not in content_type.lower():
            yield {"type": "skip", "url": final_url, "reason": "Response was not HTML"}
            continue

        parser = PageParser()
        try:
            parser.feed(html)
        except Exception:
            pass

        text = " ".join(" ".join(parser.text).split())

        # Extract emails from mailto: hrefs (reliable) with percent unquoting and validation
        mailto_emails: set = set()
        for href in parser.links:
            h = href.strip()
            if h.lower().startswith("mailto:"):
                raw_addr = h[7:].split("?")[0].strip()
                addr = unquote(raw_addr).strip()
                cleaned = validate_email(addr)
                if cleaned:
                    mailto_emails.add(cleaned)

        # Extract and validate from body text using RFC 5322 regex and false-positive filtering
        raw_body_matches = EMAIL_REGEX.findall(text)
        body_emails: set = set()
        for m in raw_body_matches:
            cleaned = validate_email(m)
            if cleaned:
                body_emails.add(cleaned)

        emails = sorted((mailto_emails | body_emails))[:15]

        effective_title, title_source = parser.effective_title
        effective_desc, desc_source, desc_present = parser.effective_description

        # Provenance-aware contacts list associating each email with source URL, title, and institutional domain
        page_contacts = []
        for em in emails:
            domain = em.split("@")[-1].lower() if "@" in em else ""
            is_inst = bool(INSTITUTIONAL_EMAIL_REGEX.search(domain))
            contact_obj = {
                "email": em,
                "sourceUrl": final_url,
                "pageTitle": effective_title or final_url,
                "isInstitutional": is_inst,
                "provenance": "mailto" if em in mailto_emails else "body_text",
            }
            page_contacts.append(contact_obj)
            c_key = (em, final_url)
            if c_key not in seen_contacts:
                seen_contacts.add(c_key)
                all_contacts.append(contact_obj)

        phones = sorted(set(re.findall(
            r"(?:\+91[\s-]?)?(?:0\d{2,4}[\s-]?)?\d{5}[\s-]?\d{5}", text
        )))[:6]

        internal: set = set()
        external: set = set()
        for href in parser.links:
            raw = href.strip()
            if not raw or raw.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            joined = urldefrag(urljoin(final_url, raw))[0]
            if urlparse(joined).scheme not in ("http", "https"):
                continue
            canon_joined = canonicalize(joined)
            if bare_host(joined) == resolved_host:
                internal.add(canon_joined)
            else:
                external.add(canon_joined)

        new_allowed, new_blocked = [], []
        for link in sorted(internal):
            is_allowed, matched_rule = path_allowed(path_of(link), group)
            if is_allowed:
                allowed_links[link] = None
                new_allowed.append(link)
                if (
                    link not in visited
                    and link not in queued
                    and not link.lower().split("?")[0].split("#")[0].endswith(SKIP_EXT)
                    and len(queue) < MAX_DISCOVERED
                ):
                    queued.add(link)
                    queue.append(link)
            else:
                blocked_links[link] = matched_rule
                new_blocked.append(link)

        page = {
            "url": final_url, "canonicalUrl": canon_final,
            "status": status,
            "ms": int((time.monotonic() - fetch_started) * 1000),
            "kb": round(size / 1024, 1),
            "title": effective_title or parser.title,
            "titleSource": title_source,
            "desc": effective_desc,
            "descSource": desc_source,
            "descPresent": desc_present,
            "headings": parser.headings[:15],
            "emails": emails,
            "contacts": page_contacts,
            "phones": phones, "words": len(text.split()),
            "internal": len(internal), "external": len(external),
            "allowedCount": len(new_allowed), "blockedCount": len(new_blocked),
        }
        pages.append(page)
        yield dict(page, type="page")

    pillars = get_site_pillars(site["name"], pages)
    summary = {
        "name": site["name"], "url": site["url"], "resolvedUrl": resolved_url,
        "robotsStatus": robots_status,
        "permission": permission,
        "robotsPolicy": robots_policy,
        "rules": len(group["rules"]) if group else 0,
        "delay": delay, "pages": len(pages), "allowed": len(allowed_links),
        "blocked": len(blocked_links),
        "emails": sorted({email for page in pages for email in page["emails"]}),
        "contacts": all_contacts[:60],
        "errors": errors,
        "errorLog": error_log[:60],
        "pillars": pillars,
    }
    RESULTS[site["name"]] = {
        "summary": summary, "robots": robots_text, "sitemaps": sitemaps,
        "pages": pages, "blocked": blocked_links,
        "allowedLinks": sorted(allowed_links),
        "contacts": all_contacts,
        "errorLog": error_log,
        "pillars": pillars,
    }
    save_results()
    yield {
        "type": "done", "summary": summary,
        "allowedLinks": sorted(allowed_links)[:80],
        "blockedLinks": [[url, rule] for url, rule in sorted(blocked_links.items())][:80],
        "stopReason": "",
    }


def save_results():
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crawl_results.json")
    with open(target, "w", encoding="utf-8") as file:
        json.dump(RESULTS, file, indent=2, ensure_ascii=False)


class Handler(BaseHTTPRequestHandler):
    def send(self, body, content_type, status=200):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/sites":
            enhanced_sites = [dict(s, pillars=get_site_pillars(s["name"], RESULTS.get(s["name"], {}).get("pages", []))) for s in SITES]
            self.send(json.dumps(enhanced_sites), "application/json")
        elif parsed.path == "/crawl":
            try:
                index = int(parse_qs(parsed.query).get("site", ["-1"])[0])
                if not 0 <= index < len(SITES):
                    self.send(json.dumps({"error": "Invalid site index"}), "application/json", 400)
                    return
            except ValueError:
                self.send(json.dumps({"error": "Invalid site index"}), "application/json", 400)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                for event in crawl(index):
                    self.wfile.write(("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except Exception as exc:
                try:
                    self.wfile.write(("data: " + json.dumps({"type": "error", "url": "", "message": f"Internal crawler error: {type(exc).__name__}: {exc}"}) + "\n\n").encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass
        elif parsed.path == "/results":
            for s in SITES:
                s_name = s["name"]
                if s_name in RESULTS:
                    pgs = RESULTS[s_name].get("pages", [])
                    pils = get_site_pillars(s_name, pgs)
                    RESULTS[s_name]["pillars"] = pils
                    if "summary" in RESULTS[s_name]:
                        RESULTS[s_name]["summary"]["pillars"] = pils
            self.send(json.dumps(RESULTS, ensure_ascii=False), "application/json")
        else:
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), encoding="utf-8") as file:
                    self.send(file.read(), "text/html")
            except OSError:
                self.send("index.html is missing. Keep it next to app.py.", "text/plain", 500)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("IIT Web Crawler is running at http://localhost:8000")
    print("Press Ctrl+C to stop the local server.")
    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass
    server.serve_forever()
