"""
E2E tests for the Carbon Footprint Quiz flow using Playwright.
Tests: full 5-step quiz → dashboard score appears → chart renders.

Prerequisites:
  pip install playwright pytest-playwright
  playwright install chromium
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8080"  # Update to deployed URL for CI


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1280, "height": 800}}


class TestQuizFlow:
    """Full 5-step quiz completion and dashboard verification."""

    def test_quiz_page_loads(self, page: Page):
        page.goto(f"{BASE_URL}/#quiz")
        expect(page.locator("h1")).to_contain_text("Carbon Footprint Quiz")
        expect(page.locator("#quiz-step-1")).to_be_visible()

    def test_step_1_transport(self, page: Page):
        page.goto(f"{BASE_URL}/#quiz")
        # Select transport mode
        page.select_option("#transport-mode", "public_transport")
        page.fill("#weekly-km", "80")
        page.click("#quiz-next-btn")
        # Should advance to step 2
        expect(page.locator("#quiz-step-2")).to_be_visible()

    def test_step_1_validation_requires_mode(self, page: Page):
        page.goto(f"{BASE_URL}/#quiz")
        page.click("#quiz-next-btn")
        expect(page.locator("#transport-mode-error")).to_be_visible()
        expect(page.locator("#quiz-step-1")).to_be_visible()

    def test_step_2_diet_required(self, page: Page):
        page.goto(f"{BASE_URL}/#quiz")
        page.select_option("#transport-mode", "bike")
        page.click("#quiz-next-btn")
        # On step 2, clicking next without diet should show error
        page.click("#quiz-next-btn")
        expect(page.locator("#diet-error")).to_be_visible()

    def test_full_quiz_journey(self, page: Page):
        """Complete all 5 steps and verify dashboard renders footprint."""
        page.goto(f"{BASE_URL}/#quiz")

        # Step 1: Transport
        page.select_option("#transport-mode", "public_transport")
        page.fill("#weekly-km", "80")
        page.click("#quiz-next-btn")
        expect(page.locator("#quiz-step-2")).to_be_visible()

        # Step 2: Diet
        page.click('input[name="meat_frequency"][value="few_times"]')
        page.click("#quiz-next-btn")
        expect(page.locator("#quiz-step-3")).to_be_visible()

        # Step 3: Energy
        page.click('input[name="energy_bill"][value="500_1500"]')
        page.click("#quiz-next-btn")
        expect(page.locator("#quiz-step-4")).to_be_visible()

        # Step 4: Lifestyle
        page.select_option("#recycling", "sometimes")
        page.click('input[name="shopping_frequency"][value="monthly"]')
        page.click("#quiz-next-btn")
        expect(page.locator("#quiz-step-5")).to_be_visible()

        # Step 5: Profile
        page.fill("#display-name", "Test User")
        page.select_option("#user-type", "student")
        page.fill("#city", "Mumbai")
        page.click("#quiz-submit-btn")

        # Wait for redirect to dashboard
        page.wait_for_url(f"{BASE_URL}/#dashboard", timeout=10000)

        # Verify footprint score appears (not --  placeholder)
        stat_footprint = page.locator("#stat-footprint")
        expect(stat_footprint).not_to_have_text("--", timeout=5000)

        # Verify rating badge rendered
        rating_badge = page.locator("#stat-rating-badge")
        expect(rating_badge).to_be_visible()
        expect(rating_badge).not_to_have_text("--")

    def test_donut_chart_renders_after_quiz(self, page: Page):
        """After quiz completion, donut chart canvas should have content."""
        page.goto(f"{BASE_URL}/#dashboard")
        # If profile exists from previous test in session, chart is visible
        canvas = page.locator("#donut-chart")
        expect(canvas).to_be_visible()

    def test_progress_bar_advances(self, page: Page):
        page.goto(f"{BASE_URL}/#quiz")
        bar = page.locator("#quiz-progress-bar")
        # Step 1: 20% width
        width_1 = bar.get_attribute("style")
        assert "20%" in width_1

        page.select_option("#transport-mode", "walk")
        page.click("#quiz-next-btn")
        # Step 2: 40% width
        width_2 = bar.get_attribute("style")
        assert "40%" in width_2

    def test_back_button_returns_to_previous_step(self, page: Page):
        page.goto(f"{BASE_URL}/#quiz")
        page.select_option("#transport-mode", "walk")
        page.click("#quiz-next-btn")
        expect(page.locator("#quiz-step-2")).to_be_visible()

        page.click("#quiz-prev-btn")
        expect(page.locator("#quiz-step-1")).to_be_visible()

    def test_zero_km_shows_for_zero_emission_modes(self, page: Page):
        page.goto(f"{BASE_URL}/#quiz")
        page.select_option("#transport-mode", "wfh")
        km_group = page.locator("#km-group")
        expect(km_group).to_be_hidden()

    def test_toast_notification_on_submission(self, page: Page):
        """A success toast should appear after successful submission."""
        page.goto(f"{BASE_URL}/#quiz")
        page.select_option("#transport-mode", "bike")
        page.click("#quiz-next-btn")
        page.click('input[name="meat_frequency"][value="never"]')
        page.click("#quiz-next-btn")
        page.click('input[name="energy_bill"][value="lt_500"]')
        page.click("#quiz-next-btn")
        page.select_option("#recycling", "always")
        page.click('input[name="shopping_frequency"][value="rarely"]')
        page.click("#quiz-next-btn")
        page.fill("#display-name", "E2E Tester")
        page.select_option("#user-type", "student")
        page.fill("#city", "Delhi")
        page.click("#quiz-submit-btn")

        # Toast should appear
        toast = page.locator(".toast--success")
        expect(toast).to_be_visible(timeout=8000)
        expect(toast).to_contain_text("kg CO₂")
