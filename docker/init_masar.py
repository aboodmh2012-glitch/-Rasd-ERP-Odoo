# -*- coding: utf-8 -*-
# MASAR bootstrap — runs once after first DB init via `odoo-bin shell`.

COMPANY_NAME_AR = "شركة مسار العالمية للأنظمة والحلول المالية"
COMPANY_NAME_EN = "MASAR Global for Financial Systems & Solutions"
BRAND = "MASAR"

Lang = env["res.lang"].with_context(active_test=False)

def ensure_lang(xmlid, code):
    lang = env.ref(xmlid, raise_if_not_found=False) or Lang.search([("code", "=", code)], limit=1)
    if not lang:
        print(f"[masar] Language not found: {code}")
        return Lang.browse()
    if not lang.active:
        installer = env["base.language.install"].create({
            "lang_ids": [(6, 0, [lang.id])],
            "overwrite": False,
        })
        installer.lang_install()
        lang.invalidate_recordset()
    return lang

ar = ensure_lang("base.lang_ar", "ar_001")
en = ensure_lang("base.lang_en", "en_US")

company = env.company
company_vals = {
    "name": COMPANY_NAME_AR,
}
if "masar_brand_name" in company._fields:
    company_vals["masar_brand_name"] = BRAND
if "email" in company._fields:
    company_vals["email"] = "info@masar.sa"
if "website" in company._fields:
    company_vals["website"] = "https://masar.sa"
sar = env.ref("base.SAR", raise_if_not_found=False)
if sar and "currency_id" in company._fields:
    company_vals["currency_id"] = sar.id
company.write(company_vals)

partner = company.partner_id
partner_vals = {"name": COMPANY_NAME_AR, "is_company": True}
if ar and "lang" in partner._fields:
    partner_vals["lang"] = ar.code
partner.write(partner_vals)

admin = env.ref("base.user_admin")
admin_vals = {"name": "MASAR Admin"}
if ar and "lang" in admin._fields:
    admin_vals["lang"] = ar.code
if "tz" in admin._fields:
    admin_vals["tz"] = "Asia/Riyadh"
admin.write(admin_vals)

Website = env["website"]
website = Website.search([], limit=1) or Website.create({"name": BRAND})
ws_vals = {"name": BRAND}
if "company_id" in website._fields:
    ws_vals["company_id"] = company.id
if ar and "default_lang_id" in website._fields:
    ws_vals["default_lang_id"] = ar.id
if "language_ids" in website._fields:
    lang_ids = [l.id for l in (ar | en) if l]
    if lang_ids:
        ws_vals["language_ids"] = [(6, 0, lang_ids)]
website.write(ws_vals)

ICP = env["ir.config_parameter"].sudo()
ICP.set_param("masar.brand", BRAND)
ICP.set_param("masar.company_name_ar", COMPANY_NAME_AR)
ICP.set_param("masar.company_name_en", COMPANY_NAME_EN)
ICP.set_param("masar.bootstrap_done", "1")

env.cr.commit()
print("[masar] Bootstrap complete:", COMPANY_NAME_AR, "/", BRAND)
