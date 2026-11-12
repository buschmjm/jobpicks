"""Static HTML pages (privacy policy, marketing, etc.)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

_STATIC_PAGES = Path(__file__).resolve().parent.parent / "static" / "pages"

PRIVACY_POLICY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Privacy Policy — JobPicks</title>
  <style>
    body {
      font-family: system-ui, sans-serif;
      max-width: 720px;
      margin: 2rem auto;
      padding: 0 1rem;
      line-height: 1.6;
      color: #1a1a1a;
    }
    h1 { font-size: 1.75rem; }
    h2 { font-size: 1.15rem; margin-top: 1.5rem; }
    a { color: #2563eb; }
  </style>
</head>
<body>
  <h1>Privacy Policy</h1>
  <p><em>Last updated: September 2, 2026</em></p>
  <p>This policy describes how JobPicks (&ldquo;we&rdquo;, &ldquo;us&rdquo;) handles personal
  information for job seekers in the United States. We do not sell personal information.</p>

  <h2>Information we collect</h2>
  <ul>
    <li><strong>Account:</strong> email address and name via Keycloak SSO (we do not store passwords).</li>
    <li><strong>Profile &amp; resume:</strong> uploaded PDF/DOCX files and parsed profile fields you confirm.</li>
    <li><strong>Usage:</strong> swipe actions, apply to-do status, and product analytics events.</li>
    <li><strong>Billing:</strong> subscription status via Stripe (payment details stay with Stripe).</li>
  </ul>

  <h2>How we use information</h2>
  <p>We use your data to provide job matching, apply workflows, optional email digests, and
  AI-assisted features (career advisor, application packets, resume tailoring). Resume and job
  content may be sent to AI providers acting as processors on our behalf. We do not use your
  resume to train public models or share it with employers without your action.</p>

  <h2>Sub-processors</h2>
  <ul>
    <li>Stripe (payments)</li>
    <li>Cloudflare (network delivery)</li>
    <li>Email delivery provider (transactional email)</li>
    <li>AI inference providers (when cloud LLM is enabled)</li>
  </ul>

  <h2>Retention</h2>
  <ul>
    <li>Account data until you delete your account.</li>
    <li>LLM call logs and product telemetry: 90 days.</li>
    <li>Stripe billing records: 7 years (tax/legal).</li>
    <li>Resume files on disk: deleted on account deletion; otherwise purged after 90 days.</li>
  </ul>

  <h2>Your rights</h2>
  <ul>
    <li><strong>Access / portability:</strong> export JSON via Settings or
    <code>GET /api/privacy/export</code> while signed in.</li>
    <li><strong>Delete:</strong> Settings &rarr; Delete account, or
    <code>DELETE /api/privacy/delete-my-data</code>.</li>
    <li><strong>Opt out of sale:</strong> we do not sell personal information (CCPA).</li>
    <li><strong>Marketing email:</strong> unsubscribe link in digests; preferences in Settings.</li>
  </ul>

  <h2>Security</h2>
  <p>Traffic is encrypted in transit. Resume uploads are size-limited and processed in isolated
  workers; we never execute uploaded files.</p>

  <h2>Contact</h2>
  <p>Privacy requests: <a href="mailto:privacy@jbuschmann.com">privacy@jbuschmann.com</a></p>
  <p>See also our <a href="/terms">Terms of Service</a>.</p>
</body>
</html>
"""

TERMS_OF_SERVICE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Terms of Service — JobPicks</title>
  <style>
    body {
      font-family: system-ui, sans-serif;
      max-width: 720px;
      margin: 2rem auto;
      padding: 0 1rem;
      line-height: 1.6;
      color: #1a1a1a;
    }
    h1 { font-size: 1.75rem; }
    h2 { font-size: 1.15rem; margin-top: 1.5rem; }
    a { color: #2563eb; }
  </style>
</head>
<body>
  <h1>Terms of Service</h1>
  <p><em>Last updated: September 4, 2026</em></p>
  <p>These Terms of Service (&ldquo;Terms&rdquo;) govern your access to and use of JobPicks
  at <a href="https://jobs.jbuschmann.com">jobs.jbuschmann.com</a> and related mobile
  applications (the &ldquo;Service&rdquo;), operated by Willow River Automation
  (&ldquo;we&rdquo;, &ldquo;us&rdquo;, &ldquo;our&rdquo;). By creating an account or using
  the Service, you agree to these Terms and our <a href="/privacy">Privacy Policy</a>.</p>

  <h2>1. Eligibility</h2>
  <p>You must be at least 18 years old and legally able to work in the United States to use
  the Service. You are responsible for the accuracy of information you provide, including
  resume content and job preferences.</p>

  <h2>2. The Service</h2>
  <p>JobPicks helps job seekers discover roles, manage an apply to-do list, and use
  AI-assisted tools for career guidance, resume editing, and application preparation.
  JobPicks does <strong>not</strong> submit job applications on your behalf without your
  review and action. Job listings are aggregated from third-party sources and may be
  outdated, incomplete, or inaccurate.</p>

  <h2>3. Accounts</h2>
  <p>Accounts are authenticated through our identity provider (Keycloak). You are
  responsible for safeguarding your credentials and for activity under your account.
  Notify us promptly at <a href="mailto:privacy@jbuschmann.com">privacy@jbuschmann.com</a>
  if you suspect unauthorized access.</p>

  <h2>4. Plans and billing</h2>
  <ul>
    <li><strong>Free plan:</strong> limited daily deck matches, AI advisor messages, resume
    builder messages, and lifetime application packet generation, as shown in the app.</li>
    <li><strong>Pro plan:</strong> expanded limits and features as described at checkout.
    Subscriptions are billed monthly through Stripe unless canceled.</li>
    <li>Prices may vary (e.g., promotional A/B pricing). Taxes may apply where required.</li>
    <li>You may cancel Pro at any time; access continues through the end of the paid period.</li>
    <li>Refunds are handled case-by-case unless required by law. Contact
    <a href="mailto:privacy@jbuschmann.com">privacy@jbuschmann.com</a>.</li>
  </ul>

  <h2>5. AI-generated content</h2>
  <p>AI features produce drafts and suggestions only. You must review all generated content
  before using it in applications, emails, or interviews. We do not guarantee accuracy,
  completeness, or fitness for a particular role. AI output is not legal, financial, or
  career counseling advice.</p>

  <h2>6. Acceptable use</h2>
  <p>You agree not to:</p>
  <ul>
    <li>Use the Service for unlawful purposes or to misrepresent your qualifications.</li>
    <li>Scrape, reverse engineer, or overload our systems.</li>
    <li>Share account access or resell the Service without permission.</li>
    <li>Upload malware or content you do not have rights to use.</li>
  </ul>

  <h2>7. Intellectual property</h2>
  <p>We retain rights in the Service, software, and branding. You retain rights in your
  resume and profile content. You grant us a limited license to process your content to
  operate the Service (matching, AI features, storage, backups).</p>

  <h2>8. Third-party services</h2>
  <p>The Service integrates with third parties (e.g., Stripe, job board APIs, AI
  providers). Their terms and privacy policies apply to those interactions. We are not
  responsible for third-party sites you visit via job links.</p>

  <h2>9. Disclaimers</h2>
  <p>THE SERVICE IS PROVIDED &ldquo;AS IS&rdquo; WITHOUT WARRANTIES OF ANY KIND. WE DO NOT
  GUARANTEE EMPLOYMENT, INTERVIEWS, OR RESPONSES FROM EMPLOYERS. JOB LISTINGS MAY BE
  EXPIRED OR INACCURATE.</p>

  <h2>10. Limitation of liability</h2>
  <p>TO THE MAXIMUM EXTENT PERMITTED BY LAW, WE ARE NOT LIABLE FOR INDIRECT, INCIDENTAL,
  SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF PROFITS, DATA, OR GOODWILL.
  OUR TOTAL LIABILITY FOR ANY CLAIM RELATING TO THE SERVICE IS LIMITED TO THE GREATER OF
  USD $100 OR THE AMOUNT YOU PAID US IN THE TWELVE MONTHS BEFORE THE CLAIM.</p>

  <h2>11. Termination</h2>
  <p>You may delete your account in Settings. We may suspend or terminate access for
  violations of these Terms or to protect the Service. Sections that by nature should
  survive (billing records, disclaimers, limitations) survive termination.</p>

  <h2>12. Changes</h2>
  <p>We may update these Terms. Material changes will be posted on this page with an updated
  date. Continued use after changes constitutes acceptance.</p>

  <h2>13. Governing law</h2>
  <p>These Terms are governed by the laws of the State of Minnesota, USA, without regard to
  conflict-of-law rules. Disputes shall be resolved in courts located in Minnesota, unless
  applicable law requires otherwise.</p>

  <h2>14. Contact</h2>
  <p>Questions about these Terms:
  <a href="mailto:privacy@jbuschmann.com">privacy@jbuschmann.com</a></p>
  <p>See also our <a href="/privacy">Privacy Policy</a>.</p>
</body>
</html>
"""


@router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy() -> HTMLResponse:
    """Simple privacy policy page with CCPA disclosure basics (plan §12)."""
    return HTMLResponse(content=PRIVACY_POLICY_HTML)


@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
async def terms_of_service() -> HTMLResponse:
    """Terms of Service for public launch and app store listings."""
    return HTMLResponse(content=TERMS_OF_SERVICE_HTML)


@router.get("/welcome", response_class=HTMLResponse, include_in_schema=False)
async def marketing_welcome() -> HTMLResponse:
    """Public marketing page for Play Store URL and organic discovery."""
    html = (_STATIC_PAGES / "welcome.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)
