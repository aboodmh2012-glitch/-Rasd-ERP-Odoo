"""Tests for M7 analytics: calendar-aware durations and team aggregates."""

from datetime import datetime, timedelta

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import make_mon_fri_calendar


@tagged("post_install", "-at_install")
class TestHelpdeskAnalytics(TransactionCase):
    """resolution_hours/open_hours duration math and team-level aggregates."""

    @classmethod
    def setUpClass(cls):  # pylint: disable=invalid-name
        """A team on a Mon-Fri 9-17 calendar, and its closed stage."""
        super().setUpClass()
        calendar = make_mon_fri_calendar(cls.env, name="Analytics calendar")
        cls.team = cls.env["helpdesk.team"].create(
            {
                "name": "Analytics Team",
                "calendar_id": calendar.id,
                "csat_enabled": False,
            }
        )
        cls.closed_stage = cls.env["helpdesk.stage"].search(
            [("is_closed", "=", True)], limit=1
        )

    def test_resolution_hours_uses_calendar_working_hours(self):
        """Thursday 4pm -> Friday 12pm on a Mon-Fri 9-17 calendar is 4
        working hours -- the same fixture already verified for SLA
        deadlines in test_sla.py, applied to get_work_duration_data.

        create_date/close_date/stage_id are all patched via raw SQL in one
        shot rather than through an ORM write(): writing stage_id would
        trigger the close-trigger logic in write(), which sets close_date
        to the real "now" and marks resolution_hours to-compute -- a later
        framework-triggered recompute would then re-derive it from a stale
        mix of the patched create_date and that real close_date instead of
        the values this test actually wants to assert on.
        """
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Duration check", "team_id": self.team.id}
        )
        self.env.cr.execute(
            "UPDATE helpdesk_ticket "
            "SET create_date = %s, close_date = %s, stage_id = %s "
            "WHERE id = %s",
            (
                datetime(2024, 1, 4, 16, 0, 0),  # Thursday
                datetime(2024, 1, 5, 12, 0, 0),  # Friday
                self.closed_stage.id,
                ticket.id,
            ),
        )
        ticket.invalidate_recordset()
        ticket._compute_resolution_hours()  # pylint: disable=protected-access

        self.assertEqual(ticket.resolution_hours, 4.0)

    def test_open_hours_frozen_after_close(self):
        """open_hours stops growing once the ticket is closed."""
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Freeze check", "team_id": self.team.id}
        )
        ticket.stage_id = self.closed_stage
        frozen_value = ticket.open_hours

        # Backdate create_date far into the past: if the freeze guard were
        # broken, recomputing would show a large jump in open_hours.
        self.env.cr.execute(
            "UPDATE helpdesk_ticket SET create_date = %s WHERE id = %s",
            (datetime(2020, 1, 1, 9, 0, 0), ticket.id),
        )
        ticket.invalidate_recordset(["create_date"])
        ticket._compute_open_hours()  # pylint: disable=protected-access

        self.assertEqual(ticket.open_hours, frozen_value)

    def test_team_sla_compliance_percentage(self):
        """sla_compliance is the % of SLA-tracked, closed tickets that met
        their deadline."""
        self.env["helpdesk.sla"].create(
            {
                "name": "Compliance SLA",
                "team_id": self.team.id,
                "target_hours": 100,
            }
        )
        met_ticket = self.env["helpdesk.ticket"].create(
            {"name": "Met SLA", "team_id": self.team.id}
        )
        met_ticket.stage_id = self.closed_stage
        self.assertTrue(met_ticket.sla_reached)

        breached_ticket = self.env["helpdesk.ticket"].create(
            {"name": "Breached SLA", "team_id": self.team.id}
        )
        past = fields.Datetime.now() - timedelta(hours=1)
        self.env.cr.execute(
            "UPDATE helpdesk_ticket SET sla_deadline = %s WHERE id = %s",
            (past, breached_ticket.id),
        )
        breached_ticket.invalidate_recordset(["sla_deadline"])
        breached_ticket.stage_id = self.closed_stage
        self.assertFalse(breached_ticket.sla_reached)

        self.assertEqual(self.team.sla_compliance, 50.0)

    def test_team_avg_resolution_hours(self):
        """avg_resolution_hours averages resolution_hours across the
        team's closed tickets."""
        first = self.env["helpdesk.ticket"].create(
            {"name": "Quick one", "team_id": self.team.id}
        )
        first.stage_id = self.closed_stage
        second = self.env["helpdesk.ticket"].create(
            {"name": "Slow one", "team_id": self.team.id}
        )
        second.stage_id = self.closed_stage

        # Isolate the aggregation from calendar-duration math, already
        # covered by test_resolution_hours_uses_calendar_working_hours.
        first.write({"resolution_hours": 10.0})
        second.write({"resolution_hours": 20.0})

        self.assertEqual(self.team.avg_resolution_hours, 15.0)
