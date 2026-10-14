"""Demo data: a fictional design studio with two mailboxes. Used by DEMO_MODE and for the README screenshots."""

import random
import time

COMPANY = {"name": "Northwind Studio",
           "description": "Brand and web design studio. Clients are mid-size B2B companies; we use Figma, Webflow, "
                          "Stripe and Notion. Partners include Webflow's Enterprise partner program."}
MAILBOXES = ["hello@northwind.studio", "maya@northwind.studio"]

# sender domain -> (label the demo classifier picks, needs attention)
DEMO_ROUTES = {
    "acmecorp.com": ("Clients/Acme Corp", False),
    "globex.io": ("Clients/Globex", False),
    "initech.co": ("Clients/Initech", False),
    "brightline.ai": ("Leads/Brightline", False),
    "solsticehealth.com": ("Leads/Solstice Health", False),
    "webflow.com": ("Partners/Webflow", False),
    "stripe.com": ("Finance", False),
    "figma.com": ("Vendors/Figma", False),
    "aws.amazon.com": ("Vendors/AWS", False),
    "greenhouse.io": ("Hiring", False),
    "docusign.net": ("Legal/Contracts", False),
    "github.com": ("Notifications", False),
    "substack.com": ("Newsletters", False),
    "smashingmagazine.com": ("Newsletters", False),
    "sidebar.io": ("Newsletters", False),
    "google.com": ("Notifications", False),
    "vercel.com": ("Notifications", False),
    "linear.app": ("Notifications", False),
}

SAMPLES = [
    ("Priya Raman <priya@acmecorp.com>", "Homepage v3 feedback", "Loved the hero, two small notes on the pricing table before Friday's review"),
    ("Priya Raman <priya@acmecorp.com>", "Re: Brand guidelines PDF", "Thanks! Sharing with our marketing team today."),
    ("Marcus Lee <marcus@acmecorp.com>", "Q4 campaign landing pages", "Can we add two more landing pages to the current sprint?"),
    ("Tom Becker <tom@globex.io>", "Kickoff agenda for next week", "Here is a draft agenda for the discovery workshop on Tuesday"),
    ("Tom Becker <tom@globex.io>", "Re: Moodboard round 2", "Option B is the clear favourite internally"),
    ("Lena Ortiz <lena@initech.co>", "Can you send the revised SOW?", "Legal is waiting on the updated scope to approve the next phase"),
    ("Raj Patel <raj@initech.co>", "Webflow staging access", "Could you add our new dev to the staging site?"),
    ("Daniel Kim <daniel@brightline.ai>", "Interested in a website rebuild", "Saw your Webflow work. Do you have time for a call this week?"),
    ("Ana Silva <ana@solsticehealth.com>", "Question about your pricing", "We're comparing three studios for a Q1 rebrand"),
    ("Webflow Partners <partners@webflow.com>", "You're approved: Webflow Enterprise Partner", "Welcome to the Enterprise partner program"),
    ("Webflow Partners <partners@webflow.com>", "New lead routed to you: Fernhill Bank", "A Webflow Enterprise prospect requested a certified partner"),
    ("Stripe <receipts@stripe.com>", "Your receipt from Northwind Studio #4021", "Payment of $4,800.00 received from Acme Corp"),
    ("Stripe <billing@stripe.com>", "Payment failed for invoice INV-208", "We couldn't charge the card on file for Globex"),
    ("Stripe <receipts@stripe.com>", "Payout of $12,340.00 is on its way", "Expected to arrive in your bank account on Oct 16"),
    ("Figma <billing@figma.com>", "Your Figma Organization renewal", "Your annual plan renews on Nov 2"),
    ("AWS Notifications <no-reply@aws.amazon.com>", "Budget alert: 80% of monthly budget", "Your budget 'studio-hosting' has exceeded 80%"),
    ("Greenhouse <no-reply@greenhouse.io>", "New application: Senior Product Designer", "Jordan Lee applied to Senior Product Designer"),
    ("Greenhouse <no-reply@greenhouse.io>", "Interview scheduled: Motion Designer", "Sam Chen, Thursday 3pm with Maya"),
    ("DocuSign <dse@docusign.net>", "Please sign: Master Services Agreement - Initech", "Lena Ortiz sent you a document to review and sign"),
    ("Vercel <notifications@vercel.com>", "Deploy failed: northwind-site", "Build failed on main after 42s"),
    ("Vercel <notifications@vercel.com>", "Deployment ready: acme-landing", "Preview deployment is ready"),
    ("Linear <notifications@linear.app>", "Weekly report: Website team", "12 issues completed, 3 in progress"),
    ("GitHub <noreply@github.com>", "[northwind/site] Dependabot alert", "A moderate severity vulnerability was found"),
    ("Google Workspace <workspace-noreply@google.com>", "Security alert: new sign-in on Mac", "A new sign-in to maya@northwind.studio"),
    ("Lenny's Newsletter <lenny@substack.com>", "How the best teams run design reviews", "This week's issue: design critique rituals"),
    ("Smashing Magazine <newsletter@smashingmagazine.com>", "Smashing Newsletter Issue #512", "Container queries in production, a deep dive"),
    ("Sidebar <hello@sidebar.io>", "Sidebar: 5 design links", "The best design links, every weekday"),
    ("Framer <hello@framer.com>", "Framer Conf: 30% off tickets this week", "Join us in Amsterdam, early-bird ends Friday"),
    ("Canva <marketing@canva.com>", "Introducing Canva AI for teams", "Launch week: new features for brand kits"),
    ("Josh from GrowthLeads <josh@growthleads.biz>", "Quick question about your outbound", "We help agencies book 20 calls a month, invite you to a demo"),
    ("Notion <team@makenotion.com>", "What's new in Notion Calendar", "Plan your week with new scheduling features"),
    ("Dribbble <hello@dribbble.com>", "Your shot got 120 likes", "Acme rebrand case study is trending"),
]


def demo_inboxes():
    rng = random.Random(7)
    now = time.time() * 1000
    boxes = {m: [] for m in MAILBOXES}
    for n, (sender, subject, snippet) in enumerate(SAMPLES, 1):
        box = MAILBOXES[n % 2]
        boxes[box].append({
            "id": f"demo{n:04d}", "thread": f"t{n:04d}", "ts": int(now - rng.uniform(5, 400) * 3600 * 1000),
            "from": sender, "to": box, "subject": subject, "snippet": snippet,
            "bulk": any(k in sender.lower() for k in ("newsletter", "marketing", "hello@", "notifications")),
            "unread": rng.random() < 0.6, "inbox": True, "user_labels": []})
    for box in boxes.values():
        box.sort(key=lambda m: -m["ts"])
    return boxes
