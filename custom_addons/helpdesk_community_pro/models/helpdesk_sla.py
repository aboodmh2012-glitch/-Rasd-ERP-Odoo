"""Helpdesk SLA policy: target resolution hours per team/priority/tag."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import api, fields, models

from .helpdesk_ticket import HELPDESK_PRIORITY_SELECTION


class HelpdeskSla(models.Model):  # pylint: disable=too-few-public-methods
    """A target-hours policy matched to tickets by team, priority and tag.

    Matching specificity (most specific wins): team+priority+tag >
    team+priority > team alone. priority and tag_id are both optional
    narrowing dimensions; team_id is the only required match key.
    """

    _name = "helpdesk.sla"
    _description = "Helpdesk SLA Policy"
    _order = "team_id, priority desc, id"

    name = fields.Char(required=True)
    team_id = fields.Many2one("helpdesk.team", required=True, index=True)
    priority = fields.Selection(
        HELPDESK_PRIORITY_SELECTION, help="Leave empty to match any priority."
    )
    tag_id = fields.Many2one(
        "helpdesk.tag", help="Leave empty to match tickets with any (or no) tags."
    )
    target_hours = fields.Float(
        required=True, help="Working hours allowed to resolve a matching ticket."
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )

    @api.model
    def _search_best_match(self, team, priority, tags):
        """Return the single most specific active policy for a ticket's
        team/priority/tags, or an empty recordset if none applies."""
        if not team:
            return self.browse()
        candidates = self.search([("team_id", "=", team.id)])
        matches = candidates.filtered(
            lambda sla: (not sla.priority or sla.priority == priority)
            and (not sla.tag_id or sla.tag_id in tags)
        )
        if not matches:
            return self.browse()
        return max(
            matches,
            key=lambda sla: (2 if sla.priority else 0) + (1 if sla.tag_id else 0),
        )
