# EduCrawler 🎓

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Tests Passing](https://img.shields.io/badge/tests-25%20passed-brightgreen.svg)](test_crawler.py)
[![RFC Compliance](https://img.shields.io/badge/RFC-3986%20%7C%209309-orange.svg)](https://www.rfc-editor.org/rfc/rfc9309)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An academic Information Retrieval (IR) web crawler and institutional intelligence system designed to politely index, verify, and organize academic data from the official websites of India's **10 Premier IITs**.

---

## 🌟 Key Features

1. **Polite & Ethical Crawling:**
   - Strict **RFC 9309** compliance (`robots.txt` verification before any page is fetched).
   - Enforced **2.0-second politeness cooldown** between requests.
   - Bounded per-site page budgets and visited URL frontiers to prevent runaway crawls.

2. **Conservative URL Canonicalization (RFC 3986):**
   - Normalizes schemes and hostnames while **preserving `www.`** routing.
   - Automatically removes default ports (`:80`, `:443`) and fragments (`#...`).
   - Safely encodes spaces into `%20` without corrupting pre-existing valid percent-escapes.
   - Preserves query parameter ordering and semantics.

3. **Secure Verified TLS/SSL:**
   - Full hostname validation and certificate trust store verification via `certifi`.
   - Eliminates insecure fallback contexts to guarantee end-to-end transport integrity.

4. **Precision HTML Parsing & Email Extraction:**
   - Automatically skips non-content elements (`<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`).
   - Decodes obfuscated and hex-encoded `mailto:` links.
   - RFC 5322 regex validation that strictly filters out minified code artifacts (`bundle@1.2.js`), framework tokens (`react@18.2.0`), and static image assets (`logo@2x.png`).
   - Classifies institutional domains (`.ac.in`, `.ernet.in`) with page provenance.

5. **3-Pillar Academic Dossier (Universal Across All 10 IITs):**
   - **🏛️ Pillar 1: Branches & Departments:** Core engineering disciplines, department directory links, total branch counts, and specialized research centers.
   - **🎓 Pillar 2: Admissions Gateways:** UG (JEE Advanced), PG (GATE/JAM), Doctoral (Ph.D.), and portal links.
   - **💼 Pillar 3: Training & Placement (T&P):** Placement bodies (OCS, CDC, SPO, T&P), recruiter portals, and verified contact emails with 1-click clipboard copy.
   - **Explicit Provenance:** Delineates curated catalog facts from live crawl discoveries.

6. **Interactive Editorial UI & Live Telemetry:**
   - Real-time Server-Sent Events (SSE) telemetry showing HTTP status, latency, politeness cooldowns, and frontiers.
   - 10-institute comparison table and dossier card views.

7. **Modular Jupyter Notebook (`iit_crawler_pipeline.ipynb`):**
   - Teacher-friendly, block-by-block implementation with zero complex jargon.
   - Explains what each block does, which library it uses, and why.
   - Includes a **Teacher Presentation & Viva Cheat Sheet**.

---

## 🏛️ Covered Institutions

| # | Institute | Region | Department Directory | Placement Office |
|---|---|---|---|---|
| **1** | **IIT Bombay** | Western Zone | [Directory](https://www.iitb.ac.in/en/academics/departments) | Training & Placement Cell (T&P) |
| **2** | **IIT Delhi** | Northern Zone | [Directory](https://home.iitd.ac.in/departments.php) | Office of Career Services (OCS) |
| **3** | **IIT Madras** | Southern Zone | [Directory](https://www.iitm.ac.in/academics/departments) | Placement Office & Career Development |
| **4** | **IIT Kanpur** | Northern Zone | [Directory](https://www.iitk.ac.in/department) | Students' Placement Office (SPO) |
| **5** | **IIT Kharagpur** | Eastern Zone | [Directory](https://www.iitkgp.ac.in/academics) | Career Development Centre (CDC) |
| **6** | **IIT Roorkee** | Northern Zone | [Directory](https://www.iitr.ac.in/Departments) | Placement and Internship Cell (PIC) |
| **7** | **IIT Guwahati** | North-Eastern Zone | [Directory](https://www.iitg.ac.in/acad/departments) | Centre for Career Development (CCD) |
| **8** | **IIT Hyderabad** | Southern Zone | [Directory](https://iith.ac.in/academics/departments) | Office of Career Services (OCS) |
| **9** | **IIT Indore** | Central Zone | [Directory](https://www.iiti.ac.in/academics/departments) | Training and Placement Cell (T&P) |
| **10** | **IIT Gandhinagar** | Western Zone | [Directory](https://iitgn.ac.in/academics/departments) | Career Development Services (CDS) |

---

## 🚀 Quick Start

### 1. Run the Web Application
```bash
python app.py
```
Open **`http://localhost:8000`** in your browser.

### 2. Run the Modular Jupyter Notebook
```bash
jupyter notebook iit_crawler_pipeline.ipynb
```
Or execute it headless to generate pre-computed outputs:
```bash
python -m nbconvert --to notebook --execute --inplace iit_crawler_pipeline.ipynb
```

### 3. Run the Automated Test Suite
```bash
python -m unittest test_crawler.py -v
```

---

## 📂 Repository Structure

```
EduCrawler/
├── app.py                      # Core multi-threaded HTTP server & BFS crawler pipeline
├── index.html                  # Interactive editorial UI with live SSE telemetry stream
├── test_crawler.py             # 25-point automated test suite (RFC compliance, URL, email, TLS)
├── iit_crawler_pipeline.ipynb  # Modular, student-friendly Jupyter Notebook (block-by-block)
├── crawl_results.json          # Cached multi-campus crawl data with 3-pillar dossiers
├── README.md                   # Project documentation & architectural guide
└── .gitignore                  # Git ignore rules
```

---

## 📜 Ethical Crawling & RFC Compliance Notice
This project is built strictly for educational and academic research. It complies with:
- **RFC 9309:** Robots Exclusion Protocol (respecting explicit and wildcard rules, crawl delays, and precedence).
- **RFC 3986:** Uniform Resource Identifier (URI) Generic Syntax.
- **RFC 5322:** Internet Message Format address validation.
