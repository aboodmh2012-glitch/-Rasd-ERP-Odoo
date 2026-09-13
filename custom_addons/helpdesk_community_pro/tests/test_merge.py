"""Tests for the ticket merge wizard: messages, followers, attachments, guards."""

import base64

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestHelpdeskTicketMerge(TransactionCase):
    """Merging moves messages/followers/attachments and closes the source."""

    @classmethod
    def setUpClass(cls):  # pylint: disable=invalid-name
        """A team and a closed stage shared by every test."""
        super().setUpClass()
        cls.team = cls.env["helpdesk.team"].create({"name": "Merge Team"})
        cls.closed_stage = cls.env["helpdesk.stage"].search(
            [("is_closed", "=", True)], limit=1
        )
        cls.partner = cls.env["res.partner"].create(
            {"name": "Merge Customer", "email": "merge@example.com"}
        )

    def _create_ticket(self, name, **vals):
        return self.env["helpdesk.ticket"].create(
            {"name": name, "team_id": self.team.id, **vals}
        )

    def test_merge_moves_messages_followers_attachments_and_closes_source(self):
        """A full merge relocates content and leaves both tickets cross-referenced."""
        destination = self._create_ticket("Destination")
        source = self._create_ticket("Source", partner_id=self.partner.id)
        source.message_subscribe(partner_ids=[self.partner.id])
        source.message_post(body="Original issue detail")
        attachment = self.env["ir.attachment"].create(
            {
                "name": "screenshot.png",
                "res_model": "helpdesk.ticket",
                "res_id": source.id,
                "datas": base64.b64encode(b"fake image data"),
            }
        )

        wizard = self.env["helpdesk.ticket.merge"].create(
            {"destination_ticket_id": destination.id, "source_ticket_id": source.id}
        )
        wizard.action_merge()

        self.assertTrue(
            any("Original issue detail" in m.body for m in destination.message_ids)
        )
        self.assertIn(self.partner, destination.message_partner_ids)
        self.assertEqual(attachment.res_id, destination.id)
        self.assertTrue(source.stage_id.is_closed)
        self.assertTrue(
            any(destination.ref in (m.body or "") for m in source.message_ids)
        )
        self.assertTrue(
            any(source.ref in (m.body or "") for m in destination.message_ids)
        )

    def test_merge_skips_csat_email_for_source(self):
        """Closing the source via merge isn't a real resolution, so it must
        not queue a CSAT survey for the customer."""
        self.team.csat_enabled = True
        destination = self._create_ticket("Destination 2")
        source = self._create_ticket("Source 2", partner_email="csat-skip@example.com")
        wizard = self.env["helpdesk.ticket.merge"].create(
            {"destination_ticket_id": destination.id, "source_ticket_id": source.id}
        )
        wizard.action_merge()
        self.assertFalse(
            source.rating_token, "a merge-close must not queue a CSAT survey"
        )

    def test_merge_rejects_closed_ticket(self):
        """Guard: both tickets must be open -- and nothing moves if rejected."""
        destination = self._create_ticket("Destination 3")
        source = self._create_ticket("Source 3")
        source.stage_id = self.closed_stage
        message_count_before = len(destination.message_ids)
        wizard = self.env["helpdesk.ticket.merge"].create(
            {"destination_ticket_id": destination.id, "source_ticket_id": source.id}
        )
        with self.assertRaises(UserError):
            wizard.action_merge()
        self.assertEqual(
            len(destination.message_ids),
            message_count_before,
            "a rejected merge must not have moved anything",
        )

    def test_merge_rejects_self_merge(self):
        """Guard: a ticket can't be merged into itself."""
        ticket = self._create_ticket("Solo")
        wizard = self.env["helpdesk.ticket.merge"].create(
            {"destination_ticket_id": ticket.id, "source_ticket_id": ticket.id}
        )
        with self.assertRaises(UserError):
            wizard.action_merge()
