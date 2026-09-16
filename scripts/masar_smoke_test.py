#!/usr/bin/env python3
"""Smoke tests for a live MASAR Odoo instance (XML-RPC)."""
from __future__ import annotations

import argparse
import io
import sys
import xmlrpc.client


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="Base URL, e.g. https://masar-xxx.up.railway.app")
    p.add_argument("--db", default="masar")
    p.add_argument("--user", default="admin")
    p.add_argument("--password", required=True)
    args = p.parse_args()
    base = args.url.rstrip("/")

    print("== common ==")
    common = xmlrpc.client.ServerProxy(f"{base}/xmlrpc/2/common", allow_none=True)
    version = common.version()
    print("version:", version.get("server_version"), version.get("server_serie"))
    uid = common.authenticate(args.db, args.user, args.password, {})
    if not uid:
        print("LOGIN FAILED")
        return 1
    print("login: OK uid=", uid)

    models = xmlrpc.client.ServerProxy(f"{base}/xmlrpc/2/object", allow_none=True)

    def call(model, method, *a, **kw):
        return models.execute_kw(args.db, uid, args.password, model, method, list(a), kw)

    print("== company ==")
    company = call("res.company", "search_read", [], ["name"], limit=1)[0]
    print("company:", company["name"])

    print("== website ==")
    import urllib.request
    with urllib.request.urlopen(base + "/", timeout=60) as resp:
        html = resp.read(2000)
        print("website HTTP", resp.status, "bytes", len(html))

    print("== contacts ==")
    partner_id = call(
        "res.partner",
        "create",
        {"name": "MASAR Smoke Contact", "email": "smoke@masar.test", "is_company": False},
    )
    print("contact id:", partner_id)

    print("== crm ==")
    lead_id = call(
        "crm.lead",
        "create",
        {"name": "MASAR Smoke Opportunity", "partner_id": partner_id, "type": "opportunity"},
    )
    print("lead id:", lead_id)

    print("== sales ==")
    order_id = call(
        "sale.order",
        "create",
        {"partner_id": partner_id},
    )
    print("sale order id:", order_id)

    print("== attachment ==")
    import base64
    payload = base64.b64encode(b"MASAR persistence smoke attachment\n").decode()
    att_id = call(
        "ir.attachment",
        "create",
        {
            "name": "masar_smoke.txt",
            "type": "binary",
            "datas": payload,
            "res_model": "res.partner",
            "res_id": partner_id,
            "mimetype": "text/plain",
        },
    )
    print("attachment id:", att_id)
    att = call("ir.attachment", "read", [att_id], ["store_fname", "file_size", "checksum"])[0]
    print("attachment meta:", att)

    print("ALL SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
