"""
Test script — verifies lead qualification with 5 sample job descriptions.
Runs the LeadAnalyzer against each sample and prints results.
"""

import sys
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from upwork_scraper.analyzer import LeadAnalyzer
from rich.console import Console
from rich.table import Table

console = Console()


SAMPLE_DESCRIPTIONS = [
    # ─── Sample 1: Strong company lead with website and founder ───
    {
        "title": "Full Stack Developer for Fintech Platform",
        "description": """
We are a fast-growing fintech startup called PayFlow.io. Our platform helps small businesses
manage payments and invoicing. We are looking for a senior full stack developer to join our team.

Founded by John Smith (CEO) in 2021, PayFlow has raised $5M in seed funding and serves over
10,000 businesses. Our website is https://payflow.io and you can reach us at hello@payflow.io.

We need someone with strong React, Node.js, and MongoDB experience to help build out our
dashboard and API integrations. This is a long-term opportunity with potential for growth.

Location: San Francisco (remote-friendly)
Budget: $80-120/hr
        """.strip(),
        "expected_priority": "GREEN",
        "expected_score_min": 50,
    },
    # ─── Sample 2: Lead with business email ───
    {
        "title": "React Native Developer for Mobile App",
        "description": """
We need a React Native developer to build a cross-platform mobile app for our e-commerce business.

Our company sells handmade furniture online through our Shopify store. We want to create a
mobile app to improve our customer experience and increase sales.

Please email your portfolio to hiring@craftedgoods.com. We are based in Austin, TX and this
would be a remote position initially but could become full-time.

Budget: $5,000-$8,000 for the initial project
        """.strip(),
        "expected_priority": "GREEN",
        "expected_score_min": 50,
    },
    # ─── Sample 3: Lead with only relevant technical keywords ───
    {
        "title": "Looking for WordPress Developer with SEO Knowledge",
        "description": """
Hello, I run a small online store where I sell handmade products. I am looking for a
WordPress developer who can help me with my e-commerce website. This is my side business
and I want to improve the online presence.

I need someone who knows Elementor, WooCommerce, and basic SEO. I need help with theme
customization and setting up payment gateways with PayPal and Stripe.

Please send me your previous work samples. My budget is around $300-$500 for this project.
This could lead to ongoing work if things work out well.

Technologies needed: WordPress, Elementor, WooCommerce, PayPal, Stripe
        """.strip(),
        "expected_priority": "YELLOW",
        "expected_score_min": 25,
    },
    # ─── Sample 4: Student or homework project ───
    {
        "title": "Need Help with Python Assignment",
        "description": """
Hi, I am a computer science student and I need help with my Python homework assignment.

The assignment is about building a simple web scraper using BeautifulSoup and requests.
It is due next week and I need someone to complete it for me. This is for my university
course.

This is a student project so my budget is very limited (max $20). Please help me complete
this assignment. I only need the code, no documentation needed.
        """.strip(),
        "expected_priority": "RED",
        "expected_score_min": 0,
    },
    # ─── Sample 5: Spam / low-quality lead ───
    {
        "title": "Make Money Fast! Work From Home!",
        "description": """
EARN BIG MONEY FROM HOME! Limited time offer! Click here to join our program and
start earning $5000/week working just 2 hours a day! No experience needed!

This is a FREE opportunity to achieve financial freedom and get rich quick. 
Act now! This offer won't last long! Passive income system that pays you daily!

No technical skills needed. Just follow our simple system and watch the money roll in.
Join thousands of successful members who are already living the dream!
        """.strip(),
        "expected_priority": "RED",
        "expected_score_min": 0,
    },
]


def run_tests():
    console.rule("[bold blue]Lead Qualification Test Suite")
    console.print("Testing 5 sample job descriptions against LeadAnalyzer\n")

    analyzer = LeadAnalyzer()
    all_passed = True
    results = []

    for i, sample in enumerate(SAMPLE_DESCRIPTIONS, 1):
        title = sample["title"]
        desc = sample["description"]

        try:
            analysis = analyzer.analyze(
                title=title,
                description=desc,
            )

            passed = True
            reasons = []

            # Check priority
            if analysis.priority != sample["expected_priority"]:
                passed = False
                reasons.append(
                    f"Expected priority {sample['expected_priority']}, got {analysis.priority}"
                )

            # Check score minimum
            if analysis.lead_score < sample["expected_score_min"]:
                passed = False
                reasons.append(
                    f"Expected score >= {sample['expected_score_min']}, got {analysis.lead_score}"
                )

            if passed:
                all_passed = False if all_passed is False else True

            results.append((i, title, analysis, passed, reasons))

        except Exception as exc:
            all_passed = False
            results.append((i, title, None, False, [f"Exception: {exc}"]))

    # Print detailed results
    for i, title, analysis, passed, reasons in results:
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        priority_color = {
            "GREEN": "[green]",
            "YELLOW": "[yellow]",
            "RED": "[red]",
        }.get(analysis.priority if analysis else "RED", "")

        console.print(f"\n[bold]Sample {i}:[/bold] {title}")
        console.print(f"  Status: {status}")
        console.print(f"  Priority: {priority_color}{analysis.priority if analysis else 'N/A'}[/]")
        console.print(f"  Score: {analysis.lead_score if analysis else 0}/100")

        if analysis:
            console.print(f"  Company Name: {analysis.company_name}")
            console.print(f"  Company Website: {analysis.company_website}")
            console.print(f"  Company Domain: {analysis.company_domain}")
            console.print(f"  Email: {analysis.email}")
            console.print(f"  Business Email: {analysis.business_email}")
            console.print(f"  Phone: {analysis.phone}")
            console.print(f"  LinkedIn: {analysis.linkedin_url}")
            console.print(f"  Decision Maker: {analysis.decision_maker_name} ({analysis.decision_maker_title})")
            console.print(f"  Budget: {analysis.budget}")
            console.print(f"  Timeline: {analysis.timeline}")
            console.print(f"  Location: {analysis.location}")
            console.print(f"  Industry: {analysis.industry}")
            console.print(f"  Technologies: {analysis.technologies}")
            console.print(f"  Services: {analysis.services_required}")
            console.print(f"  Qualification Reason: {analysis.qualification_reason}")

        if not passed:
            for r in reasons:
                console.print(f"  [red]  Reason: {r}[/red]")

    # Summary table
    console.print("\n")
    console.rule("[bold]Summary")
    table = Table(show_lines=True)
    table.add_column("Sample", style="cyan")
    table.add_column("Title", style="cyan")
    table.add_column("Priority", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Result", justify="center")

    for i, title, analysis, passed, _ in results:
        p = analysis.priority if analysis else "N/A"
        color = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}.get(p, "white")
        result_str = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        table.add_row(
            str(i),
            title[:50] + ("..." if len(title) > 50 else ""),
            f"[{color}]{p}[/{color}]",
            str(analysis.lead_score if analysis else 0),
            result_str,
        )

    console.print(table)

    passed_count = sum(1 for _, _, _, passed, _ in results if passed)
    total = len(results)
    console.print(f"\n[bold]{'All tests passed!' if passed_count == total else f'{passed_count}/{total} tests passed'}[/bold]")

    return all_passed


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
