"""Helpdesk stage: kanban pipeline step for tickets."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import fields, models


class HelpdeskStage(models.Model):  # pylint: disable=too-few-public-methods
    """A kanban pipeline stage shared by helpdesk tickets."""

    _name = "helpdesk.stage"
    _description = "Helpdesk Stage"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(
        string="Folded in Kanban",
        help="This stage is folded in the kanban view when there are no "
        "records to display in it.",
    )
    is_closed = fields.Boolean(
        string="Closing Stage",
        help="Tickets in this stage are considered closed.",
    )
    mail_template_id = fields.Many2one(
        "mail.template",
        string="Email Template",
        help="Email automatically sent to the customer when a ticket "
        "enters this stage.",
    )
