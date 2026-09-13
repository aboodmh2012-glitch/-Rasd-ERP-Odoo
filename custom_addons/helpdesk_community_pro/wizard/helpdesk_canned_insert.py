"""Wizard: insert a canned response into a ticket's chatter as a reply."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import api, fields, models


class HelpdeskCannedInsert(models.TransientModel):
    """Pick a canned response and post it as a reply on the ticket.

    Server-side picker, not composer injection (PROJECT_BLUEPRINT.md §4:
    "NO custom OWL JS in v1") -- posting straight to the chatter reuses
    the same message_post/mail-gateway path a normal agent reply takes,
    so the customer receives it exactly like any other reply.
    """

    _name = "helpdesk.canned.insert"
    _description = "Insert Canned Response"

    ticket_id = fields.Many2one("helpdesk.ticket", required=True)
    team_id = fields.Many2one(related="ticket_id.team_id")
    canned_response_id = fields.Many2one(
        "helpdesk.canned.response",
        string="Canned Response",
        required=True,
        domain="['|', ('team_ids', '=', False), ('team_ids', 'in', [team_id])]",
    )
    body_preview = fields.Html(
        related="canned_response_id.body", string="Preview", readonly=True
    )

    @api.model
    def default_get(self, fields_list):
        """Default ticket_id from the ticket form this wizard was opened from."""
        defaults = super().default_get(fields_list)
        if "ticket_id" in fields_list and not defaults.get("ticket_id"):
            defaults["ticket_id"] = self.env.context.get("active_id")
        return defaults

    def action_insert(self):
        """Post the chosen canned response's body as a reply, then close."""
        self.ensure_one()
        self.ticket_id.message_post(
            body=self.canned_response_id.body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        return {"type": "ir.actions.act_window_close"}
