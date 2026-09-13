"""Portal controllers: a customer views and replies to their own tickets.

Security follows the pattern documented in PROJECT_BLUEPRINT.md §8: the
detail route always goes through the base controller's own
_document_check_access (explicit access check, no record id trusted from
the URL without it); the list route relies on the helpdesk_ticket_rule_portal
ir.rule to scope results, exactly like core's own project/sale portals do
-- no redundant hand-rolled domain to drift out of sync with the rule.
Replies are posted through the stock portal chatter widget
(portal.message_thread), which itself falls back to the current portal
user's normal access rights when no share token is present.
"""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import _, http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from odoo.http import request


class HelpdeskCustomerPortal(CustomerPortal):
    """ "My Tickets" portal pages: list, detail, and reply via chatter."""

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "ticket_count" in counters:
            ticket_model = request.env["helpdesk.ticket"]
            values["ticket_count"] = (
                ticket_model.search_count([])
                if ticket_model.check_access_rights("read", raise_exception=False)
                else 0
            )
        return values

    def _ticket_get_searchbar_sortings(self):
        return {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "name": {"label": _("Subject"), "order": "name"},
        }

    @http.route(
        ["/my/tickets", "/my/tickets/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tickets(self, page=1, sortby=None, **kw):
        # pylint: disable=unused-argument
        # **kw absorbs stray query-string params (e.g. from pager links)
        # so an unexpected one doesn't turn into a TypeError on this route.
        """List the current portal user's own tickets (ir.rule-filtered)."""
        values = self._prepare_portal_layout_values()
        ticket_model = request.env["helpdesk.ticket"]

        searchbar_sortings = self._ticket_get_searchbar_sortings()
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]

        ticket_count = ticket_model.search_count([])
        pager = portal_pager(
            url="/my/tickets",
            url_args={"sortby": sortby},
            total=ticket_count,
            page=page,
            step=self._items_per_page,
        )
        tickets = ticket_model.search(
            [], order=order, limit=self._items_per_page, offset=pager["offset"]
        )
        values.update(
            {
                "tickets": tickets,
                "page_name": "ticket",
                "pager": pager,
                "default_url": "/my/tickets",
                "searchbar_sortings": searchbar_sortings,
                "sortby": sortby,
            }
        )
        return request.render("helpdesk_community_pro.portal_my_tickets", values)

    @http.route(["/my/ticket/<int:ticket_id>"], type="http", auth="user", website=True)
    def portal_ticket_detail(self, ticket_id, access_token=None, **kw):
        """A single ticket, with its status and chatter for replies."""
        try:
            ticket_sudo = self._document_check_access(
                "helpdesk.ticket", ticket_id, access_token=access_token
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._get_page_view_values(
            ticket_sudo,
            access_token,
            {"page_name": "ticket"},
            "my_tickets_history",
            False,
            **kw,
        )
        return request.render("helpdesk_community_pro.portal_ticket_page", values)
