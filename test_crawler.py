"""
Automated Test Suite for IIT Web Crawler
========================================
Covers:
  1. Conservative URL Canonicalization (RFC 3986): host/scheme lowercasing, www preservation,
     default port stripping, fragment removal, query preservation, and space percent-encoding.
  2. Secure TLS Configuration: Strict hostname and certificate verification without unverified fallbacks.
  3. Robots.txt RFC 9309 Compliance: multi-agent grouping, agent selection, empty Disallow,
     wildcard matching, end-anchors ($), and longest-match Allow vs Disallow precedence.
  4. Content Parsing & Metadata Extraction: title provenance, meta vs og vs fallback descriptions,
     and boilerplate suppression.
  5. Precision Email Extraction & Validation: RFC 5322 regex validation, percent-unquoting,
     filtering of JavaScript/image false positives, and institutional domain classification.
  6. Academic Dossier Provenance: Explicit separation between curated baseline and live crawl extractions.
"""

import ssl
import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import urllib.parse

from app import (
    canonicalize,
    bare_host,
    path_of,
    parse_robots,
    pick_group,
    path_allowed,
    fetch_robots,
    PageParser,
    validate_email,
    EMAIL_REGEX,
    INSTITUTIONAL_EMAIL_REGEX,
    SITES,
    ACADEMIC_PILLARS,
    get_site_pillars,
    _SSL_CTX,
)


class TestConservativeURLCanonicalization(unittest.TestCase):
    """Test conservative RFC 3986 URL normalization to prevent duplicate fetches without altering semantics."""

    def test_default_port_stripping(self):
        # Default ports (80 for HTTP, 443 for HTTPS) stripped, www preserved
        self.assertEqual(
            canonicalize("http://www.iitb.ac.in:80/about"),
            "http://www.iitb.ac.in/about"
        )
        self.assertEqual(
            canonicalize("https://www.iitd.ac.in:443/research"),
            "https://www.iitd.ac.in/research"
        )

    def test_custom_port_preserved(self):
        # Non-default ports must not be stripped
        self.assertEqual(
            canonicalize("http://internal.iitb.ac.in:8080/portal"),
            "http://internal.iitb.ac.in:8080/portal"
        )

    def test_www_prefix_preserved(self):
        # Conservative normalization preserves www. because servers/subdomains may route differently
        self.assertEqual(
            canonicalize("https://www.iitm.ac.in/academics"),
            "https://www.iitm.ac.in/academics"
        )
        self.assertEqual(
            canonicalize("https://iitm.ac.in/academics"),
            "https://iitm.ac.in/academics"
        )

    def test_scheme_and_host_lowercased(self):
        self.assertEqual(
            canonicalize("HTTPS://WWW.IITKGP.AC.IN/Academics/Index"),
            "https://www.iitkgp.ac.in/Academics/Index"
        )

    def test_redundant_slashes_collapsed(self):
        self.assertEqual(
            canonicalize("https://www.iitk.ac.in//dept///cse"),
            "https://www.iitk.ac.in/dept/cse"
        )

    def test_space_encoding_rfc3986_iit_roorkee_fix(self):
        """
        IIT Roorkee relative links with unencoded spaces (e.g. '/About the Institute/index.html')
        must be encoded as %20 to prevent InvalidURL control-character exceptions.
        """
        raw_url = "https://www.iitr.ac.in/Institute/About the Institute/index.html"
        canon = canonicalize(raw_url)
        self.assertNotIn(" ", canon)
        self.assertIn("About%20the%20Institute", canon)

    def test_query_preservation_and_fragment_removal(self):
        # Query order and values preserved; fragment stripped
        url = "https://www.iitg.ac.in/notice?id=123&type=acad#top"
        canon = canonicalize(url)
        self.assertNotIn("#top", canon)
        self.assertIn("id=123&type=acad", canon)

    def test_bare_host_helper(self):
        self.assertEqual(bare_host("https://www.iith.ac.in/events/"), "iith.ac.in")
        self.assertEqual(bare_host("http://home.iitd.ac.in/"), "home.iitd.ac.in")


class TestSecureTLSConfiguration(unittest.TestCase):
    """Verify that TLS connections strictly enforce certificate and hostname verification."""

    def test_strict_tls_context_enforced(self):
        self.assertTrue(_SSL_CTX.check_hostname, "Hostname verification must be enabled")
        self.assertEqual(_SSL_CTX.verify_mode, ssl.CERT_REQUIRED, "Certificate verification must be required")

    def test_no_insecure_fallback_context(self):
        import app
        self.assertFalse(hasattr(app, "_SSL_CTX_FALLBACK"), "_SSL_CTX_FALLBACK must be completely removed")


class TestRobotsTxtRFC9309Compliance(unittest.TestCase):
    """Test RFC 9309 compliant parsing, wildcards, end-anchors, and longest match rules."""

    def test_empty_disallow_allows_all(self):
        # RFC 9309 §2.2.1: Disallow with empty value means any path can be accessed
        txt = "User-agent: *\nDisallow:\n"
        groups, _ = parse_robots(txt)
        group = pick_group(groups)
        allowed, rule = path_allowed("/any/path", group)
        self.assertTrue(allowed)

    def test_multiple_user_agents_in_group(self):
        txt = """
User-agent: Googlebot
User-agent: IITStudentCrawler/2.0
Disallow: /admin/
"""
        groups, _ = parse_robots(txt)
        group = pick_group(groups)
        self.assertIsNotNone(group)
        self.assertIn("IITStudentCrawler/2.0", group["agents"])
        allowed, rule = path_allowed("/admin/panel", group)
        self.assertFalse(allowed)

    def test_longest_match_allow_precedence(self):
        """Under RFC 9309, longer path match wins. If same length, Allow wins."""
        txt = """
User-agent: *
Disallow: /admin/
Allow: /admin/public/
"""
        groups, _ = parse_robots(txt)
        group = pick_group(groups)

        allowed, rule = path_allowed("/admin/secret", group)
        self.assertFalse(allowed)
        self.assertEqual(rule, ["Disallow", "/admin/"])

        allowed, rule = path_allowed("/admin/public/page", group)
        self.assertTrue(allowed)
        self.assertEqual(rule, ["Allow", "/admin/public/"])

    def test_equal_length_allow_wins_tie(self):
        txt = """
User-agent: *
Disallow: /portal
Allow: /portal
"""
        groups, _ = parse_robots(txt)
        group = pick_group(groups)
        allowed, rule = path_allowed("/portal/dashboard", group)
        self.assertTrue(allowed, "Allow must win equal-length ties per RFC 9309 §2.2.2")
        self.assertEqual(rule[0], "Allow")

    def test_wildcard_and_end_anchor(self):
        txt = """
User-agent: *
Disallow: /*.pdf$
Disallow: /temp/*/cache
"""
        groups, _ = parse_robots(txt)
        group = pick_group(groups)

        # Trailing $. Disallow *.pdf$
        allowed, _ = path_allowed("/reports/annual.pdf", group)
        self.assertFalse(allowed)

        # .pdf in the middle of a filename must NOT match $
        allowed, _ = path_allowed("/reports/annual.pdf.html", group)
        self.assertTrue(allowed)

        # Wildcard in path
        allowed, _ = path_allowed("/temp/session123/cache", group)
        self.assertFalse(allowed)

    def test_crawl_delay_parsing(self):
        txt = """
User-agent: IITStudentCrawler
Crawl-delay: 3.5
Disallow: /cgi-bin/
"""
        groups, _ = parse_robots(txt)
        group = pick_group(groups)
        self.assertIsNotNone(group)
        self.assertEqual(group["delay"], 3.5)


class TestPrecisionEmailExtractionAndValidation(unittest.TestCase):
    """Test strict email regex validation, unquoting, and filtering of JS/image artifacts."""

    def test_valid_emails_accepted(self):
        valid = [
            "placement@iitb.ac.in",
            "admissions.office@home.iitd.ac.in",
            "dean_rnd@iitr.ac.in",
            "spo@iiti.ac.in",
            "contact-us@iitm.ac.in",
        ]
        for em in valid:
            self.assertEqual(validate_email(em), em.lower())

    def test_trailing_punctuation_sanitized(self):
        self.assertEqual(validate_email("dean@iitd.ac.in,"), "dean@iitd.ac.in")
        self.assertEqual(validate_email("office@iitr.ac.in;"), "office@iitr.ac.in")
        self.assertEqual(validate_email("(contact@iitb.ac.in)"), "contact@iitb.ac.in")
        self.assertEqual(validate_email("tpo@iitk.ac.in."), "tpo@iitk.ac.in")

    def test_javascript_and_asset_tokens_rejected(self):
        invalid = [
            "react@18.2.0",
            "bundle.js",
            "logo@2x.png",
            "hero-banner@mobile.jpg",
            "font@woff2",
            "webpack@5.0.0",
            "user@example.com",
            "test@domain.com",
            "error@sentry.io",
            "plainaddress",
            "@domain.com",
            "user@.com",
            "user@domain",
        ]
        for inv in invalid:
            self.assertIsNone(validate_email(inv), f"Expected {inv} to be rejected")

    def test_percent_encoded_mailto_unquoted_and_validated(self):
        raw_href = "mailto:%61%63%61%64%40%69%69%74%68%2e%61%63%2e%69%6e"
        unquoted = urllib.parse.unquote(raw_href[7:].split("?")[0].strip())
        self.assertEqual(validate_email(unquoted), "acad@iith.ac.in")

    def test_institutional_domain_classification(self):
        # Academic / Institutional
        self.assertTrue(bool(INSTITUTIONAL_EMAIL_REGEX.search("iitb.ac.in")))
        self.assertTrue(bool(INSTITUTIONAL_EMAIL_REGEX.search("admin.iitd.ac.in")))
        self.assertTrue(bool(INSTITUTIONAL_EMAIL_REGEX.search("iitr.ernet.in")))
        self.assertTrue(bool(INSTITUTIONAL_EMAIL_REGEX.search("iitgn.ac.in")))

        # External / Commercial
        self.assertFalse(bool(INSTITUTIONAL_EMAIL_REGEX.search("gmail.com")))
        self.assertFalse(bool(INSTITUTIONAL_EMAIL_REGEX.search("vendor.org")))
        self.assertFalse(bool(INSTITUTIONAL_EMAIL_REGEX.search("partner.co.in")))


class TestMetadataExtraction(unittest.TestCase):
    """Test extraction of titles, descriptions, and distinguishing missing metadata from errors."""

    def test_full_metadata_extraction(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>IIT Bombay | Home</title>
            <meta name="description" content="Premier engineering and research institute in Mumbai.">
        </head>
        <body>
            <header><nav><a href="/">Home</a></nav></header>
            <main>
                <h1>Welcome to IIT Bombay</h1>
                <p>Welcome text of length greater than twenty-five characters for body test.</p>
            </main>
        </body>
        </html>
        """
        parser = PageParser()
        parser.feed(html)

        title, title_source = parser.effective_title
        self.assertEqual(title, "IIT Bombay | Home")
        self.assertEqual(title_source, "title_tag")

        desc, desc_source, is_present = parser.effective_description
        self.assertEqual(desc, "Premier engineering and research institute in Mumbai.")
        self.assertEqual(desc_source, "meta")
        self.assertTrue(is_present)

    def test_missing_meta_description_with_paragraph_fallback(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>IIT Delhi Department</title>
        </head>
        <body>
            <h1>Department of Computer Science</h1>
            <p>This is an introductory paragraph explaining the department activities in detail.</p>
        </body>
        </html>
        """
        parser = PageParser()
        parser.feed(html)

        desc, desc_source, is_present = parser.effective_description
        self.assertFalse(is_present)
        self.assertEqual(desc_source, "first_paragraph")
        self.assertIn("introductory paragraph", desc)

    def test_boilerplate_suppression(self):
        html = """
        <html>
        <body>
            <nav><h2>Navigation Menu</h2></nav>
            <header><h3>Header Banner</h3></header>
            <footer><p>Copyright 2026</p></footer>
            <main>
                <h1>Main Content Headline</h1>
                <p>Real article paragraph that contains more than twenty-five characters.</p>
            </main>
        </body>
        </html>
        """
        parser = PageParser()
        parser.feed(html)

        heading_texts = [h[1] for h in parser.headings]
        self.assertNotIn("Navigation Menu", heading_texts)
        self.assertNotIn("Header Banner", heading_texts)
        self.assertIn("Main Content Headline", heading_texts)


class TestAcademicPillarsProvenance(unittest.TestCase):
    """Verify that all 10 IITs have complete 3-pillar data with clear provenance separation."""

    def test_all_10_institutes_have_provenance_and_pillars(self):
        self.assertEqual(len(SITES), 10, "Expected exactly 10 IITs configured")
        for site in SITES:
            name = site["name"]
            self.assertIn(name, ACADEMIC_PILLARS, f"{name} must be present in ACADEMIC_PILLARS")

            pillars = get_site_pillars(name, [])
            self.assertIn("provenance", pillars)
            self.assertTrue(pillars["provenance"]["curatedBaseline"])
            self.assertEqual(pillars["provenance"]["verificationDate"], "2026-10-14")

            # Pillar 1: Departments
            dept = pillars["departments"]
            self.assertTrue(dept.get("directoryUrl", "").startswith("http"), f"{name} directoryUrl missing")
            self.assertGreaterEqual(len(dept.get("branches", [])), 8, f"{name} must have at least 8 branches")
            self.assertEqual(dept.get("provenance"), "curated_catalog")
            self.assertEqual(dept.get("status"), "verified_portal")

            # Pillar 2: Admissions
            adm = pillars["admissions"]
            self.assertTrue(adm.get("portalUrl", "").startswith("http"), f"{name} admissions portalUrl missing")
            self.assertGreaterEqual(len(adm.get("channels", [])), 3, f"{name} must have at least 3 admission channels")
            self.assertEqual(adm.get("provenance"), "curated_catalog")
            self.assertEqual(adm.get("status"), "verified_portal")

            # Pillar 3: Placements
            plc = pillars["placements"]
            self.assertTrue(plc.get("portalUrl", "").startswith("http"), f"{name} placement portalUrl missing")
            self.assertIn("@", plc.get("contactEmail", ""), f"{name} must have valid placement contact email")
            self.assertEqual(plc.get("provenance"), "curated_catalog")
            self.assertEqual(plc.get("status"), "verified_portal")


if __name__ == "__main__":
    unittest.main()
