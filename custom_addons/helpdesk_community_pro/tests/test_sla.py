"""Tests for the SLA engine: matching, deadline math, cron, freeze."""

from datetime import datetime, timedelta

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import make_mon_fri_calendar


@tagged("post_install", "-at_install")
class TestHelpdeskSla(TransactionCase):
    """SLA policy matching, calendar-aware deadlines, cron, and freeze."""

    @classmethod
    def setUpClass(cls):  # pylint: disable=invalid-name
        """Create a team on a Mon-Fri 9-17 UTC calendar shared by all tests."""
        super().setUpClass()
        calendar = make_mon_fri_calendar(cls.env)
        cls.team = cls.env["helpdesk.team"].create(
            {"name": "SLA Team", "calendar_id": calendar.id}
        )
        cls.closed_stage = cls.env["helpdesk.stage"].search(
            [("is_closed", "=", True)], limit=1
        )

    def test_sla_matching_specificity(self):
        """The most specific matching policy wins: team+priority+tag beats
        team+priority beats team alone."""
        tag = self.env["helpdesk.tag"].create({"name": "VIP"})
        sla_team = self.env["helpdesk.sla"].create(
            {"name": "Team only", "team_id": self.team.id, "target_hours": 40}
        )
        sla_team_priority = self.env["helpdesk.sla"].create(
            {
                "name": "Team + High",
                "team_id": self.team.id,
                "priority": "2",
                "target_hours": 20,
            }
        )
        sla_team_priority_tag = self.env["helpdesk.sla"].create(
            {
                "name": "Team + High + VIP",
                "team_id": self.team.id,
                "priority": "2",
                "tag_id": tag.id,
                "target_hours": 8,
            }
        )

        ticket_all = self.env["helpdesk.ticket"].create(
            {
                "name": "Most specific",
                "team_id": self.team.id,
                "priority": "2",
                "tag_ids": [(6, 0, [tag.id])],
            }
        )
        self.assertEqual(ticket_all.sla_id, sla_team_priority_tag)

        ticket_priority_only = self.env["helpdesk.ticket"].create(
            {"name": "Priority only", "team_id": self.team.id, "priority": "2"}
        )
        self.assertEqual(ticket_priority_only.sla_id, sla_team_priority)

        ticket_team_only = self.env["helpdesk.ticket"].create(
            {"name": "Team only", "team_id": self.team.id, "priority": "0"}
        )
        self.assertEqual(ticket_team_only.sla_id, sla_team)

    def test_sla_deadline_skips_weekend(self):
        """A 4h SLA on a ticket created Thursday 4pm lands Friday noon, not
        Thursday evening or over the weekend."""
        sla = self.env["helpdesk.sla"].create(
            {"name": "4h SLA", "team_id": self.team.id, "target_hours": 4.0}
        )
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Deadline test", "team_id": self.team.id}
        )
        self.assertEqual(ticket.sla_id, sla)

        # 2024-01-04 is a Thursday. create_date is a system field, so it's
        # backdated directly in the DB and the compute is re-run by hand.
        self.env.cr.execute(
            "UPDATE helpdesk_ticket SET create_date = %s WHERE id = %s",
            (datetime(2024, 1, 4, 16, 0, 0), ticket.id),
        )
        ticket.invalidate_recordset(["create_date", "sla_deadline"])
        ticket._compute_sla_deadline()  # pylint: disable=protected-access

        self.assertEqual(ticket.sla_deadline, datetime(2024, 1, 5, 12, 0, 0))

    def test_cron_flags_breached_ticket(self):
        """The periodic cron flags an open ticket whose deadline has passed."""
        self.env["helpdesk.sla"].create(
            {"name": "Breach SLA", "team_id": self.team.id, "target_hours": 40}
        )
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Overdue", "team_id": self.team.id}
        )
        self.assertTrue(ticket.sla_id)

        past = datetime.now() - timedelta(hours=1)
        self.env.cr.execute(
            "UPDATE helpdesk_ticket SET sla_deadline = %s WHERE id = %s",
            (past, ticket.id),
        )
        ticket.invalidate_recordset(["sla_deadline"])

        # pylint: disable=protected-access
        self.env["helpdesk.ticket"]._cron_update_sla_status()
        self.assertEqual(ticket.sla_status, "breached")

    def test_sla_reached_on_close_before_deadline(self):
        """A ticket closed before its deadline is marked sla_reached."""
        self.env["helpdesk.sla"].create(
            {"name": "Comfortable SLA", "team_id": self.team.id, "target_hours": 100}
        )
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Closed in time", "team_id": self.team.id}
        )
        self.assertTrue(ticket.sla_id)
        self.assertFalse(ticket.sla_reached)

        ticket.stage_id = self.closed_stage
        self.assertTrue(ticket.sla_reached)

    def test_sla_deadline_frozen_after_close(self):
        """Editing a closed ticket's priority changes its matched policy but
        must not move the already-frozen deadline."""
        self.env["helpdesk.sla"].create(
            {
                "name": "Priority 1 SLA",
                "team_id": self.team.id,
                "priority": "1",
                "target_hours": 10,
            }
        )
        sla_priority_2 = self.env["helpdesk.sla"].create(
            {
                "name": "Priority 2 SLA",
                "team_id": self.team.id,
                "priority": "2",
                "target_hours": 30,
            }
        )
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Freeze test", "team_id": self.team.id, "priority": "1"}
        )
        ticket.stage_id = self.closed_stage
        deadline_before = ticket.sla_deadline

        ticket.priority = "2"

        self.assertEqual(ticket.sla_id, sla_priority_2, "sla_id keeps matching live")
        self.assertEqual(
            ticket.sla_deadline, deadline_before, "deadline must stay frozen"
        )
