"""Tests for the email-to-ticket gateway (message_new / message_update)."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo.addons.mail.tests.common import MailCommon
from odoo.tests import tagged
from odoo.tools import mute_logger

EMAIL_TPL = """Return-Path: <whatever-2a840@postmaster.twitter.com>
X-Original-To: {to}
Delivered-To: {to}
To: {to}
cc: {cc}
Received: by mail1.odoo.com (Postfix, from userid 10002)
    id 5DF9ABFB2A; Fri, 10 Aug 2012 16:16:39 +0200 (CEST)
Message-ID: {msg_id}
References: {references}
Date: Tue, 29 Nov 2011 12:43:21 +0530
From: {email_from}
MIME-Version: 1.0
Subject: {subject}
Content-Type: text/plain; charset=ISO-8859-1; format=flowed

Hello,

This should create a helpdesk ticket.

Thanks,
A Customer"""

MALFORMED_TPL = """To: {to}
From: not even close to a valid header block
Subject: {subject}

Body."""


@tagged("post_install", "-at_install")
class TestHelpdeskMailGateway(MailCommon):
    """Email-to-ticket: message_new / message_update via the team alias."""

    @classmethod
    def setUpClass(cls):  # pylint: disable=invalid-name
        """Create a team with an alias, and a partner to test matching."""
        super().setUpClass()
        cls.team = cls.env["helpdesk.team"].create({"name": "Support"})
        cls.team.alias_name = "support"
        cls.known_partner = cls.env["res.partner"].create(
            {"name": "Known Customer", "email": "known@example.com"}
        )

    def _alias_email(self):
        return f"support@{self.alias_domain}"

    def test_message_new_creates_ticket_known_partner(self):
        """Inbound mail from a known partner links that partner."""
        ticket = self.format_and_process(
            EMAIL_TPL,
            to=self._alias_email(),
            email_from=self.known_partner.email_formatted,
            subject="Cannot log in",
            target_model="helpdesk.ticket",
        )
        self.assertEqual(len(ticket), 1)
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.partner_id, self.known_partner)
        self.assertEqual(ticket.partner_email, self.known_partner.email)
        self.assertTrue(ticket.stage_id)
        self.assertFalse(ticket.stage_id.is_closed)
        self.assertTrue(ticket.ref and ticket.ref.startswith("TKT/"))

    def test_message_new_unknown_sender_no_partner_created(self):
        """Inbound mail from an unknown address stores raw fields only."""
        partners_before = self.env["res.partner"].search_count([])
        ticket = self.format_and_process(
            EMAIL_TPL,
            to=self._alias_email(),
            email_from="Jane Stranger <jane.stranger@example.com>",
            subject="Billing question",
            target_model="helpdesk.ticket",
        )
        self.assertEqual(len(ticket), 1)
        self.assertFalse(ticket.partner_id)
        self.assertEqual(ticket.partner_email, "jane.stranger@example.com")
        self.assertEqual(ticket.partner_name, "Jane Stranger")
        self.assertEqual(
            self.env["res.partner"].search_count([]),
            partners_before,
            "no partner should be auto-created for an unmatched sender",
        )

    def test_message_new_queues_ack_email(self):
        """A ticket created from email queues the ack template, not manual ones."""
        ticket = self.format_and_process(
            EMAIL_TPL,
            to=self._alias_email(),
            email_from=self.known_partner.email_formatted,
            subject="Ack me",
            target_model="helpdesk.ticket",
        )
        ack_mail = (
            self.env["mail.mail"]
            .sudo()
            .search([("model", "=", "helpdesk.ticket"), ("res_id", "=", ticket.id)])
        )
        self.assertEqual(len(ack_mail), 1)
        self.assertEqual(ack_mail.state, "outgoing")
        self.assertIn(ticket.ref, ack_mail.subject)
        # A rendered email_to that matches an existing partner is resolved
        # into recipient_ids instead of staying a flat string -- check both.
        self.assertTrue(
            self.known_partner.email in (ack_mail.email_to or "")
            or self.known_partner in ack_mail.recipient_ids,
            "ack email should be addressed to the known partner",
        )

        manual_ticket = self.env["helpdesk.ticket"].create(
            {"name": "Manual ticket", "team_id": self.team.id}
        )
        manual_ack = (
            self.env["mail.mail"]
            .sudo()
            .search(
                [("model", "=", "helpdesk.ticket"), ("res_id", "=", manual_ticket.id)]
            )
        )
        self.assertFalse(
            manual_ack, "manually created tickets must not get an ack email"
        )

    def test_message_update_threads_reply(self):
        """A reply to an open ticket appends to its chatter, no reopen needed."""
        ticket = self.format_and_process(
            EMAIL_TPL,
            to=self._alias_email(),
            email_from=self.known_partner.email_formatted,
            subject="Threading test",
            msg_id="<original-thread-test@example.com>",
            target_model="helpdesk.ticket",
        )
        message_count_before = len(ticket.message_ids)
        self.format_and_process(
            EMAIL_TPL,
            to=self._alias_email(),
            email_from=self.known_partner.email_formatted,
            subject="Re: Threading test",
            references="<original-thread-test@example.com>",
            target_model="helpdesk.ticket",
            msg_id="<reply-thread-test@example.com>",
        )
        self.assertGreater(len(ticket.message_ids), message_count_before)

    def test_message_update_reopens_closed_ticket(self):
        """A reply to a closed ticket moves it back to the first open stage."""
        ticket = self.format_and_process(
            EMAIL_TPL,
            to=self._alias_email(),
            email_from=self.known_partner.email_formatted,
            subject="Reopen test",
            msg_id="<original-reopen-test@example.com>",
            target_model="helpdesk.ticket",
        )
        closed_stage = self.env["helpdesk.stage"].search(
            [("is_closed", "=", True)], limit=1
        )
        ticket.stage_id = closed_stage
        self.format_and_process(
            EMAIL_TPL,
            to=self._alias_email(),
            email_from=self.known_partner.email_formatted,
            subject="Re: Reopen test",
            references="<original-reopen-test@example.com>",
            target_model="helpdesk.ticket",
            msg_id="<reply-reopen-test@example.com>",
        )
        self.assertFalse(ticket.stage_id.is_closed)

    @mute_logger(
        "odoo.addons.helpdesk_community_pro.models.helpdesk_ticket",
        "odoo.addons.mail.models.mail_thread",
    )
    def test_message_new_malformed_mail_falls_back(self):
        """Malformed inbound mail never crashes; it still creates a ticket."""
        ticket = self.format_and_process(
            MALFORMED_TPL,
            to=self._alias_email(),
            email_from="not a real header <>",
            subject="Garbled sender",
            target_model="helpdesk.ticket",
        )
        self.assertEqual(len(ticket), 1)
        self.assertEqual(ticket.team_id, self.team)
