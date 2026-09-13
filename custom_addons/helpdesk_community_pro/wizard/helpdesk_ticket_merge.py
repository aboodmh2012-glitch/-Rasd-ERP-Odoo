"""Wizard: merge one ticket into another (messages, followers, attachments)."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HelpdeskTicketMerge(models.TransientModel):
    """Merge source_ticket_id into destination_ticket_id, then close source.

    All-or-nothing: every step below is a normal ORM write inside this one
    method call, so if anything raises, Odoo rolls the whole transaction
    back -- there's nothing partially merged to clean up.
    """

    _name = "helpdesk.ticket.merge"
    _description = "Merge Helpdesk Tickets"

    destination_ticket_id = fields.Many2one(
        "helpdesk.ticket", string="Merge Into", required=True
    )
    source_ticket_id = fields.Many2one(
        "helpdesk.ticket",
        string="Ticket to Merge",
        required=True,
        domain="[('id', '!=', destination_ticket_id)]",
    )

    @api.model
    def default_get(self, fields_list):
        """Default destination_ticket_id from the ticket this wizard opened from."""
        defaults = super().default_get(fields_list)
        if "destination_ticket_id" in fields_list and not defaults.get(
            "destination_ticket_id"
        ):
            defaults["destination_ticket_id"] = self.env.context.get("active_id")
        return defaults

    def action_merge(self):
        """Move messages/followers/attachments, close the source ticket."""
        self.ensure_one()
        source = self.source_ticket_id
        destination = self.destination_ticket_id
        if source == destination:
            raise UserError(_("Cannot merge a ticket into itself."))
        if source.stage_id.is_closed or destination.stage_id.is_closed:
            raise UserError(_("Both tickets must be open to merge."))

        source.message_change_thread(destination)
        destination.message_subscribe(partner_ids=source.message_partner_ids.ids)
        self.env["ir.attachment"].search(
            [("res_model", "=", "helpdesk.ticket"), ("res_id", "=", source.id)]
        ).write({"res_id": destination.id})

        closed_stage = self.env["helpdesk.stage"].search(
            [("is_closed", "=", True)], order="sequence", limit=1
        )
        destination.message_post(
            body=_("Merged ticket %(ref)s into this one.", ref=source.ref)
        )
        # Closing here isn't a real resolution, so it shouldn't trigger a
        # CSAT survey for the customer (see helpdesk.ticket.write()).
        source.with_context(skip_csat_email=True).write({"stage_id": closed_stage.id})
        source.message_post(body=_("Merged into %(ref)s.", ref=destination.ref))

        return {
            "type": "ir.actions.act_window",
            "res_model": "helpdesk.ticket",
            "res_id": destination.id,
            "view_mode": "form",
            "target": "current",
        }
