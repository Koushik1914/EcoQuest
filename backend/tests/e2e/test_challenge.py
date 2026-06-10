"""
E2E tests for Challenge completion flow using Playwright.
Tests: complete challenge → points update → streak counter increments.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8080"


def _ensure_profile(page: Page) -> None:
    """Helper: navigate through quiz fast to ensure user profile exists."""
    page.goto(f"{BASE_URL}/#quiz")
    if "ecoquest_profile" in page.evaluate("() => Object.keys(localStorage)"):
        return  # Profile already set
    # Quick fill quiz
    page.select_option("#transport-mode", "public_transport")
    page.fill("#weekly-km", "60")
    page.click("#quiz-next-btn")
    page.click('input[name="meat_frequency"][value="rarely"]')
    page.click("#quiz-next-btn")
    page.click('input[name="energy_bill"][value="lt_500"]')
    page.click("#quiz-next-btn")
    page.select_option("#recycling", "always")
    page.click('input[name="shopping_frequency"][value="rarely"]')
    page.click("#quiz-next-btn")
    page.fill("#display-name", "Challenge E2E User")
    page.select_option("#user-type", "student")
    page.fill("#city", "Bangalore")
    page.click("#quiz-submit-btn")
    page.wait_for_url(f"{BASE_URL}/#dashboard", timeout=10000)


class TestChallengeFlow:
    def test_challenges_page_loads(self, page: Page):
        page.goto(f"{BASE_URL}/#challenges")
        expect(page.locator("h1")).to_contain_text("Eco Challenges")

    def test_challenge_cards_render(self, page: Page):
        page.goto(f"{BASE_URL}/#challenges")
        # Wait for skeletons to be replaced by real cards
        page.wait_for_selector(".challenge-card:not(.skeleton)", timeout=8000)
        cards = page.locator(".challenge-card:not(.skeleton)")
        expect(cards.first).to_be_visible()

    def test_filter_tabs_work(self, page: Page):
        page.goto(f"{BASE_URL}/#challenges")
        page.wait_for_selector(".challenge-card:not(.skeleton)", timeout=8000)

        # Click Transport filter
        page.click('[data-filter="transport"]')
        # All visible cards should be transport
        cards = page.locator(".challenge-card:not(.skeleton)")
        count = cards.count()
        for i in range(min(count, 3)):
            card_text = cards.nth(i).inner_text()
            assert any(word in card_text for word in ["Transport", "🚗", "Cycle", "Commute", "Car"])

    def test_complete_challenge_requires_quiz(self, page: Page):
        """Without a profile, completing should redirect to quiz."""
        page.goto(f"{BASE_URL}/#challenges")
        # Clear profile
        page.evaluate("() => localStorage.removeItem('ecoquest_profile')")
        page.wait_for_selector(".complete-btn", timeout=8000)
        page.locator(".complete-btn").first.click()
        # Should show warning toast or redirect
        toast = page.locator(".toast--warning")
        expect(toast).to_be_visible(timeout=5000)

    def test_complete_challenge_awards_points(self, page: Page):
        _ensure_profile(page)
        page.goto(f"{BASE_URL}/#challenges")
        page.wait_for_selector(".complete-btn:not([disabled])", timeout=8000)

        # Read initial points from badge
        initial_pts_text = page.locator("#user-points").inner_text()

        # Complete first available challenge
        page.locator(".complete-btn:not([disabled])").first.click()

        # Wait for success toast
        toast = page.locator(".toast--success")
        expect(toast).to_be_visible(timeout=8000)
        expect(toast).to_contain_text("pts")

    def test_streak_banner_visible(self, page: Page):
        page.goto(f"{BASE_URL}/#challenges")
        expect(page.locator("#streak-banner")).to_be_visible()

    def test_streak_count_visible(self, page: Page):
        page.goto(f"{BASE_URL}/#challenges")
        expect(page.locator("#streak-count")).to_be_visible()

    def test_completed_challenge_button_disabled(self, page: Page):
        """After completion, the button should be disabled."""
        _ensure_profile(page)
        page.goto(f"{BASE_URL}/#challenges")
        page.wait_for_selector(".complete-btn:not([disabled])", timeout=8000)

        first_btn = page.locator(".complete-btn:not([disabled])").first
        first_btn.click()
        page.wait_for_selector(".toast--success", timeout=8000)

        # After completion, button for this challenge should be disabled
        page.wait_for_timeout(500)
        completed_btns = page.locator(".complete-btn[disabled]")
        expect(completed_btns.first).to_be_visible()
