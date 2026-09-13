"""Tests for the customer portal: a customer sees only their own tickets."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo.tests import tagged
from odoo.tests.common import HttpCase, JsonRpcException, new_test_user


@tagged("post_install", "-at_install")
class TestHelpdeskPortal(HttpCase):
    """Portal users can reach and reply to their own tickets, nothing else."""

    @classmethod
    def setUpClass(cls):  # pylint: disable=invalid-name
        """Two unrelated portal users and a ticket owned by the first."""
        super().setUpClass()
        team = cls.env["helpdesk.team"].create({"name": "Portal Team"})
        cls.portal_user = new_test_user(
            cls.env, login="portal_customer", groups="base.group_portal"
        )
        cls.stranger = new_test_user(
            cls.env, login="portal_stranger", groups="base.group_portal"
        )
        cls.own_ticket = cls.env["helpdesk.ticket"].create(
            {
                "name": "My ticket",
                "team_id": team.id,
                "partner_id": cls.portal_user.partner_id.id,
            }
        )

    def test_portal_user_sees_own_ticket(self):
        """A portal user can open the detail page of their own ticket."""
        self.authenticate("portal_customer", "portal_customer")
        response = self.url_open(f"/my/ticket/{self.own_ticket.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.own_ticket.name.encode(), response.content)

    def test_portal_stranger_denied(self):
        """A different portal user is bounced back to /my, not the ticket."""
        self.authenticate("portal_stranger", "portal_stranger")
        response = self.url_open(f"/my/ticket/{self.own_ticket.id}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.own_ticket.name.encode(), response.content)

    def test_portal_ticket_list_scoped_to_own(self):
        """The tickets list only shows the current portal user's tickets."""
        other_team = self.env["helpdesk.team"].create({"name": "Other Team"})
        self.env["helpdesk.ticket"].create(
            {
                "name": "Not mine",
                "team_id": other_team.id,
                "partner_id": self.stranger.partner_id.id,
            }
        )
        self.authenticate("portal_customer", "portal_customer")
        response = self.url_open("/my/tickets")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.own_ticket.name.encode(), response.content)
        self.assertNotIn(b"Not mine", response.content)

    def test_portal_user_can_reply_to_own_ticket(self):
        """A portal user can post a reply on their own ticket via the chatter.

        helpdesk.ticket grants portal users perm_write=0 (read-only) in
        ir.model.access.csv, and mail.thread's default _mail_post_access
        is "write" -- without this model explicitly overriding it to
        "read", the portal composer would silently fail on every reply
        even though the ticket detail page itself renders fine. Exercises
        the real /mail/message/post route the portal chatter widget
        calls, not a direct ORM message_post() (which would bypass this
        exact access check).
        """
        self.authenticate("portal_customer", "portal_customer")
        data = self.make_jsonrpc_request(
            "/mail/message/post",
            {
                "thread_model": "helpdesk.ticket",
                "thread_id": self.own_ticket.id,
                "post_data": {"body": "Any update on this?"},
            },
        )
        self.assertTrue(data.get("message_id"))
        self.own_ticket.invalidate_recordset(["message_ids"])
        self.assertTrue(
            any(
                "Any update on this?" in (body or "")
                for body in self.own_ticket.message_ids.mapped("body")
            )
        )

    def test_portal_stranger_cannot_reply_to_others_ticket(self):
        """A portal user cannot post on a ticket that isn't theirs.

        The read-access ir.rule (helpdesk_ticket_rule_portal) already
        scopes which tickets a portal user can even find; this confirms
        relaxing _mail_post_access to "read" for replies didn't also
        relax who can reach the thread in the first place.
        """
        self.authenticate("portal_stranger", "portal_stranger")
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request(
                "/mail/message/post",
                {
                    "thread_model": "helpdesk.ticket",
                    "thread_id": self.own_ticket.id,
                    "post_data": {"body": "Sneaky reply"},
                },
            )

    def test_assignee_field_excludes_portal_users(self):
        """The "Assigned to" field must not offer portal/customer users.

        helpdesk.ticket.user_id had no domain restricting it to internal
        users, so a customer given portal access (base.group_portal)
        showed up in the "Assigned to" picker as if they were an agent
        -- found live, with a real portal customer appearing in that
        dropdown. Matches the domain already used on
        helpdesk.team.member_ids for the same reason.
        """
        domain = self.env["helpdesk.ticket"]._fields["user_id"].domain
        matching_users = self.env["res.users"].search(domain)
        self.assertNotIn(self.portal_user, matching_users)
        self.assertIn(self.env.ref("base.user_admin"), matching_users)
