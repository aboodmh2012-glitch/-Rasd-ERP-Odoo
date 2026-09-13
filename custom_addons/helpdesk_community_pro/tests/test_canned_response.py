"""Tests for canned responses: team scoping and chatter insertion."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestHelpdeskCannedResponse(TransactionCase):
    """The insert wizard posts the chosen response's body as a reply."""

    @classmethod
    def setUpClass(cls):  # pylint: disable=invalid-name
        """A ticket, a global response, and a response scoped to another team."""
        super().setUpClass()
        cls.team = cls.env["helpdesk.team"].create({"name": "Canned Team"})
        cls.other_team = cls.env["helpdesk.team"].create({"name": "Other Team"})
        cls.ticket = cls.env["helpdesk.ticket"].create(
            {"name": "Need a canned reply", "team_id": cls.team.id}
        )
        cls.global_response = cls.env["helpdesk.canned.response"].create(
            {"name": "Thanks", "body": "<p>Thanks for reaching out!</p>"}
        )
        cls.scoped_response = cls.env["helpdesk.canned.response"].create(
            {
                "name": "Other team only",
                "body": "<p>Scoped reply</p>",
                "team_ids": [(6, 0, [cls.other_team.id])],
            }
        )

    def test_insert_posts_body_to_chatter(self):
        """action_insert posts the canned response's body as a comment."""
        message_count_before = len(self.ticket.message_ids)
        wizard = self.env["helpdesk.canned.insert"].create(
            {
                "ticket_id": self.ticket.id,
                "canned_response_id": self.global_response.id,
            }
        )
        wizard.action_insert()
        self.assertGreater(len(self.ticket.message_ids), message_count_before)
        last_message = self.ticket.message_ids.sorted("id")[-1]
        self.assertIn("Thanks for reaching out", last_message.body)

    def test_default_get_defaults_ticket_from_context(self):
        """Opened from a ticket form, ticket_id defaults from active_id."""
        wizard = (
            self.env["helpdesk.canned.insert"]
            .with_context(active_id=self.ticket.id)
            .create({"canned_response_id": self.global_response.id})
        )
        self.assertEqual(wizard.ticket_id, self.ticket)

    def test_canned_response_domain_scopes_by_team(self):
        """A global (team_ids empty) response matches any team; a scoped
        one only matches its own team -- the same expression the insert
        wizard's canned_response_id domain uses."""
        own_team_candidates = self.env["helpdesk.canned.response"].search(
            ["|", ("team_ids", "=", False), ("team_ids", "in", [self.team.id])]
        )
        self.assertIn(self.global_response, own_team_candidates)
        self.assertNotIn(self.scoped_response, own_team_candidates)

        other_team_candidates = self.env["helpdesk.canned.response"].search(
            [
                "|",
                ("team_ids", "=", False),
                ("team_ids", "in", [self.other_team.id]),
            ]
        )
        self.assertIn(self.global_response, other_team_candidates)
        self.assertIn(self.scoped_response, other_team_candidates)
