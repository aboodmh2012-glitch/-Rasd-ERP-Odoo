"""Tests for the public CSAT rating endpoint: token validation and window."""

from datetime import timedelta

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import HttpCase

from .common import make_mon_fri_calendar


@tagged("post_install", "-at_install")
class TestHelpdeskRating(HttpCase):
    """Signed-token CSAT rating: valid / tampered / update window / locked."""

    @classmethod
    def setUpClass(cls):  # pylint: disable=invalid-name
        """A closed ticket with its rating_token already generated."""
        super().setUpClass()
        calendar = make_mon_fri_calendar(cls.env, name="Rating test calendar")
        team = cls.env["helpdesk.team"].create(
            {"name": "Rating Team", "calendar_id": calendar.id, "csat_enabled": True}
        )
        closed_stage = cls.env["helpdesk.stage"].search(
            [("is_closed", "=", True)], limit=1
        )
        cls.ticket = cls.env["helpdesk.ticket"].create(
            {
                "name": "Rate me",
                "team_id": team.id,
                "partner_email": "customer@example.com",
            }
        )
        cls.ticket.stage_id = closed_stage

    def test_valid_token_records_rating(self):
        """Clicking a correctly signed link records the rating."""
        self.assertTrue(self.ticket.rating_token)
        response = self.url_open(
            f"/helpdesk/rate/{self.ticket.id}/{self.ticket.rating_token}/good"
        )
        self.assertEqual(response.status_code, 200)
        self.ticket.invalidate_recordset(["rating", "rating_date"])
        self.assertEqual(self.ticket.rating, "good")
        self.assertTrue(self.ticket.rating_date)

    def test_tampered_token_rejected(self):
        """A wrong token renders the invalid page and changes nothing."""
        response = self.url_open(
            f"/helpdesk/rate/{self.ticket.id}/not-the-real-token/good"
        )
        self.assertEqual(response.status_code, 200)
        self.ticket.invalidate_recordset(["rating"])
        self.assertFalse(self.ticket.rating)

    def test_second_rating_within_window_updates(self):
        """A repeat click inside the window updates the value, not the anchor."""
        self.url_open(f"/helpdesk/rate/{self.ticket.id}/{self.ticket.rating_token}/bad")
        self.ticket.invalidate_recordset(["rating", "rating_date"])
        self.assertEqual(self.ticket.rating, "bad")
        first_rating_date = self.ticket.rating_date

        self.url_open(
            f"/helpdesk/rate/{self.ticket.id}/{self.ticket.rating_token}/good"
        )
        self.ticket.invalidate_recordset(["rating", "rating_date"])
        self.assertEqual(self.ticket.rating, "good")
        self.assertEqual(
            self.ticket.rating_date,
            first_rating_date,
            "the window's anchor shouldn't move on an update",
        )

    def test_rating_locked_after_window(self):
        """Past the update window, a click no longer changes the rating."""
        self.ticket.write(
            {
                "rating": "bad",
                "rating_date": fields.Datetime.now() - timedelta(days=8),
            }
        )
        response = self.url_open(
            f"/helpdesk/rate/{self.ticket.id}/{self.ticket.rating_token}/good"
        )
        self.assertEqual(response.status_code, 200)
        self.ticket.invalidate_recordset(["rating"])
        self.assertEqual(
            self.ticket.rating, "bad", "a locked rating must not be overwritten"
        )
