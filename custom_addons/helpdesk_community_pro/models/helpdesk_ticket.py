"""Helpdesk ticket: a single customer support request."""

import hashlib
import hmac
import logging
from datetime import timedelta

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import _, api, fields, models
from odoo.tools import consteq
from odoo.tools.mail import email_split_tuples

_logger = logging.getLogger(__name__)

RATING_SELECTION = [
    ("good", "Good"),
    ("okay", "Okay"),
    ("bad", "Bad"),
]
RATING_WINDOW_DAYS = 7

HELPDESK_PRIORITY_SELECTION = [
    ("0", "Low"),
    ("1", "Medium"),
    ("2", "High"),
    ("3", "Urgent"),
]


class HelpdeskTicket(models.Model):  # pylint: disable=too-few-public-methods
    """A customer support ticket moving through a team's stage pipeline."""

    _name = "helpdesk.ticket"
    _description = "Helpdesk Ticket"
    _inherit = ["mail.thread", "mail.activity.mixin", "portal.mixin"]
    _order = "priority desc, id desc"
    # Portal customers only have read access (ir.model.access.csv), but must
    # still be able to reply from the portal chatter -- without this, mail's
    # default _mail_post_access="write" silently blocks their composer (same
    # pattern as project.task, which portal users also comment on).
    _mail_post_access = "read"

    name = fields.Char(string="Subject", required=True, tracking=True)
    ref = fields.Char(default="New", readonly=True, copy=False)
    team_id = fields.Many2one("helpdesk.team", required=True, index=True, tracking=True)
    stage_id = fields.Many2one(
        "helpdesk.stage",
        required=True,
        index=True,
        tracking=True,
        default=lambda self: self.env["helpdesk.stage"].search(
            [], order="sequence", limit=1
        ),
        group_expand="_read_group_stage_ids",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Assigned to",
        index=True,
        tracking=True,
        domain=[("share", "=", False)],
    )
    partner_id = fields.Many2one(
        "res.partner", string="Customer", index=True, tracking=True
    )
    partner_email = fields.Char(string="Customer Email")
    partner_name = fields.Char(string="Customer Name")
    priority = fields.Selection(HELPDESK_PRIORITY_SELECTION, default="1", required=True)
    tag_ids = fields.Many2many("helpdesk.tag", string="Tags")
    description = fields.Html()
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    color = fields.Integer(string="Color Index", default=0)
    active = fields.Boolean(default=True)

    sla_id = fields.Many2one(
        "helpdesk.sla",
        string="SLA Policy",
        compute="_compute_sla_id",
        store=True,
        help="Most specific active policy matching this ticket's team, "
        "priority and tags.",
    )
    sla_deadline = fields.Datetime(
        compute="_compute_sla_deadline",
        store=True,
        index=True,
        help="Working-hours deadline from the matched SLA policy. Frozen "
        "once the ticket reaches a closed stage.",
    )
    sla_status = fields.Selection(
        [
            ("ok", "On Track"),
            ("at_risk", "At Risk"),
            ("breached", "Breached"),
        ],
        compute="_compute_sla_status",
        store=True,
        help="Frozen once the ticket reaches a closed stage.",
    )
    sla_reached = fields.Boolean(
        default=False,
        copy=False,
        help="Set when the ticket entered a closed stage before its SLA " "deadline.",
    )

    rating = fields.Selection(
        RATING_SELECTION, copy=False, help="Empty until the customer rates the ticket."
    )
    rating_token = fields.Char(
        copy=False, help="Signed token embedded in the CSAT email's rating links."
    )
    rating_date = fields.Datetime(copy=False)

    assign_date = fields.Datetime(
        copy=False, help="Set the first time the ticket is assigned to an agent."
    )
    close_date = fields.Datetime(
        copy=False, help="Set the first time the ticket enters a closed stage."
    )
    open_hours = fields.Float(
        compute="_compute_open_hours",
        store=True,
        help="Calendar-aware working hours elapsed since creation. Frozen "
        "once the ticket reaches a closed stage.",
    )
    resolution_hours = fields.Float(
        compute="_compute_resolution_hours",
        store=True,
        help="Calendar-aware working hours from creation to close_date. "
        "Zero while the ticket has never been closed.",
    )

    @api.model
    # PORT-19: group_expand callables are invoked with 2 args (records,
    # domain), not 3 (records, domain, order) as on 17.0 -- order is no
    # longer passed, so this relies on helpdesk.stage's own _order.
    def _read_group_stage_ids(self, stages, _domain):
        return stages.search([])

    def _compute_access_url(self):
        super()._compute_access_url()
        for ticket in self:
            ticket.access_url = f"/my/ticket/{ticket.id}"

    @api.depends("team_id", "priority", "tag_ids")
    def _compute_sla_id(self):
        for ticket in self:
            # pylint: disable=protected-access
            ticket.sla_id = self.env["helpdesk.sla"]._search_best_match(
                ticket.team_id, ticket.priority, ticket.tag_ids
            )

    @api.depends("sla_id", "team_id", "create_date")
    def _compute_sla_deadline(self):
        for ticket in self:
            if ticket.stage_id.is_closed:
                ticket.sla_deadline = ticket.sla_deadline  # frozen, no-op
                continue
            if not ticket.sla_id or not ticket.team_id.calendar_id:
                ticket.sla_deadline = False
                continue
            start = ticket.create_date or fields.Datetime.now()
            ticket.sla_deadline = ticket.team_id.calendar_id.plan_hours(
                ticket.sla_id.target_hours, start, compute_leaves=True
            )

    @api.depends("sla_deadline", "sla_id.target_hours")
    def _compute_sla_status(self):
        now = fields.Datetime.now()
        for ticket in self:
            if ticket.stage_id.is_closed:
                ticket.sla_status = ticket.sla_status  # frozen, no-op
                continue
            if not ticket.sla_id:
                ticket.sla_status = False
                continue
            remaining = (ticket.sla_deadline - now).total_seconds()
            if remaining <= 0:
                ticket.sla_status = "breached"
            elif remaining < 0.25 * (ticket.sla_id.target_hours * 3600):
                ticket.sla_status = "at_risk"
            else:
                ticket.sla_status = "ok"

    @api.model
    def _cron_update_sla_status(self):
        """Batch-refresh sla_status for open tickets (data/helpdesk_cron.xml).

        The @api.depends compute keeps sla_status correct the instant a
        relevant field changes, but elapsed time alone never triggers it --
        only this periodic pass catches a deadline quietly slipping into
        at_risk/breached with no field having changed.
        """
        tickets = self.search(
            [("sla_deadline", "!=", False), ("stage_id.is_closed", "=", False)]
        )
        tickets._compute_sla_status()  # pylint: disable=protected-access

    @api.depends("create_date")
    def _compute_open_hours(self):
        now = fields.Datetime.now()
        for ticket in self:
            if ticket.stage_id.is_closed:
                ticket.open_hours = ticket.open_hours  # frozen, no-op
                continue
            if not ticket.create_date or not ticket.team_id.calendar_id:
                ticket.open_hours = 0.0
                continue
            duration = ticket.team_id.calendar_id.get_work_duration_data(
                ticket.create_date, now, compute_leaves=True
            )
            ticket.open_hours = duration["hours"]

    @api.depends("close_date")
    def _compute_resolution_hours(self):
        for ticket in self:
            if (
                not ticket.close_date
                or not ticket.create_date
                or not ticket.team_id.calendar_id
            ):
                ticket.resolution_hours = 0.0
                continue
            duration = ticket.team_id.calendar_id.get_work_duration_data(
                ticket.create_date, ticket.close_date, compute_leaves=True
            )
            ticket.resolution_hours = duration["hours"]

    @api.model
    def _cron_update_open_hours(self):
        """Batch-refresh open_hours for all open tickets (data/helpdesk_cron.xml).

        Broader domain than _cron_update_sla_status on purpose: a ticket
        with no matching SLA policy still has an age worth tracking for
        analytics, it just has no deadline to breach.
        """
        tickets = self.search([("stage_id.is_closed", "=", False)])
        tickets._compute_open_hours()  # pylint: disable=protected-access

    @api.model_create_multi
    def create(self, vals_list):
        """Assign the next TKT/YYYY/NNNNN sequence value to new tickets."""
        for vals in vals_list:
            if vals.get("ref", "New") == "New":
                vals["ref"] = (
                    self.env["ir.sequence"].next_by_code("helpdesk.ticket") or "New"
                )
        tickets = super().create(vals_list)
        # Force the SLA chain to compute and flush now, while the ticket is
        # still in its just-created (open) stage. Left pending, these
        # stored fields stay "to-compute" past this method returning --
        # whatever next triggers a flush (e.g. a later write closing the
        # ticket) would recompute them then, and the closed-stage freeze
        # guard in _compute_sla_deadline/_compute_sla_status would see its
        # own field still mid-computation and freeze it at the empty
        # default instead of the real value it should have captured while
        # still open.
        tickets.flush_recordset(
            ["sla_id", "sla_deadline", "sla_status", "open_hours", "resolution_hours"]
        )
        return tickets

    def write(self, vals):
        """Set sla_reached/close_date/CSAT request on the transition into a
        closed stage, and assign_date on first assignment.

        sla_deadline/sla_status are frozen simply by not depending on
        stage_id -- this write is only about capturing point-in-time facts
        (transitions) that a depends-based compute can't see, it only sees
        resulting states.

        context key `skip_csat_email`: used by the merge wizard when it
        closes the source ticket -- that closure isn't a real resolution,
        so it shouldn't survey the customer.
        """
        newly_closing = self.browse()
        if vals.get("stage_id"):
            new_stage = self.env["helpdesk.stage"].browse(vals["stage_id"])
            if new_stage.is_closed:
                newly_closing = self.filtered(lambda t: not t.stage_id.is_closed)

        newly_assigned = self.browse()
        if vals.get("user_id"):
            newly_assigned = self.filtered(
                lambda t: not t.user_id and not t.assign_date
            )

        result = super().write(vals)

        if newly_assigned:
            newly_assigned.assign_date = fields.Datetime.now()

        if newly_closing:
            now = fields.Datetime.now()
            for ticket in newly_closing:
                if ticket.sla_id:
                    ticket.sla_reached = now <= ticket.sla_deadline
                ticket.close_date = now
                if ticket.team_id.csat_enabled and not self.env.context.get(
                    "skip_csat_email"
                ):
                    # pylint: disable=protected-access
                    ticket.rating_token = ticket._get_rating_token()
                    ticket._send_rating_email()
        return result

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """Create a ticket from an inbound email (see mail.thread).

        team_id comes from the alias's own defaults (helpdesk.team's
        _alias_get_creation_values), not from anything parsed here.
        """
        defaults = dict(custom_values or {})
        defaults.setdefault("name", msg_dict.get("subject") or _("No Subject"))
        defaults.setdefault("description", msg_dict.get("body"))
        # pylint: disable=broad-except
        # Inbound mail must never crash the gateway: any unexpected shape
        # here (missing/garbled headers) falls back to a bare ticket.
        try:
            email_from = msg_dict.get("email_from") or ""
            pairs = email_split_tuples(email_from)
            name, email = pairs[0] if pairs else ("", email_from)
            defaults.setdefault("partner_email", email)
            defaults.setdefault("partner_name", name or email)
            if msg_dict.get("author_id"):
                defaults.setdefault("partner_id", msg_dict["author_id"])
        except Exception:
            _logger.warning(
                "helpdesk: could not parse sender %r on inbound email %r, "
                "falling back to a bare ticket",
                msg_dict.get("email_from"),
                msg_dict.get("message_id"),
                exc_info=True,
            )
        ticket = super().message_new(msg_dict, custom_values=defaults)
        ticket._send_ack_email()  # pylint: disable=protected-access
        return ticket

    def message_update(self, msg_dict, update_vals=None):
        """Reopen a closed ticket when the customer replies (see mail.thread).

        Threading the reply into the chatter itself is already handled by
        the mail gateway (message_post, called separately by
        _message_route_process) -- this only needs the reopen side effect.
        """
        open_stage = self.env["helpdesk.stage"].search(
            [("is_closed", "=", False)], order="sequence", limit=1
        )
        for ticket in self:
            if ticket.stage_id.is_closed and open_stage:
                ticket.stage_id = open_stage
        return super().message_update(msg_dict, update_vals=update_vals)

    def _send_ack_email(self):
        """Queue the "ticket received" acknowledgement for email-created tickets."""
        self.ensure_one()
        if not self.partner_email:
            return
        template = self.env.ref(
            "helpdesk_community_pro.mail_template_ticket_received",
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=False)

    def _get_rating_token(self):
        """Deterministic signature for this ticket's public rating links.

        hmac(db secret, ticket id) rather than a stored random value: the
        public rating controller re-derives the same signature from the
        URL's ticket_id and compares, so a token can never be replayed
        against a different ticket_id. Still stored on the field (set once,
        on close) purely so the mail template can render object.rating_token
        directly without calling into Python.
        """
        self.ensure_one()
        secret = self.env["ir.config_parameter"].sudo().get_param("database.secret")
        payload = f"helpdesk.ticket-rating-{self.id}".encode()
        return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    def _rating_token_is_valid(self, token):
        self.ensure_one()
        return bool(token) and consteq(token, self._get_rating_token())

    def _apply_rating(self, rating):
        """Record a customer's CSAT click; returns False if the window has
        closed.

        First click sets rating + rating_date. Further clicks update the
        rating value as long as they land within RATING_WINDOW_DAYS of that
        *first* rating_date (rating_date itself never moves, so the window
        doesn't reset/slide with each click) -- past it, the rating is
        locked and this returns False without writing anything.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        if self.rating_date and now > self.rating_date + timedelta(
            days=RATING_WINDOW_DAYS
        ):
            return False
        vals = {"rating": rating}
        if not self.rating_date:
            vals["rating_date"] = now
        self.write(vals)
        return True

    def _send_rating_email(self):
        """Queue the CSAT "how did we do" email for a just-closed ticket."""
        self.ensure_one()
        if not self.partner_email:
            return
        template = self.env.ref(
            "helpdesk_community_pro.mail_template_ticket_rating",
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=False)
