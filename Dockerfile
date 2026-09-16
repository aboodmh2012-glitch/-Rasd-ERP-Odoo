# MASAR runtime image — Odoo 19 Community (official) + MASAR custom addons.
# Full Odoo source remains in the git repo for development; Docker build
# excludes it via .dockerignore to stay within Railway build limits.
FROM odoo:19.0

USER root

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    ODOO_RC=/etc/odoo/odoo.conf \
    ODOO_DATA_DIR=/var/lib/odoo

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl \
        postgresql-client \
        rtlcss \
        fonts-noto-core \
        fonts-noto-ui-core \
    && rm -rf /var/lib/apt/lists/*

# MASAR custom addons (independent from Rasd modules)
COPY custom_addons /mnt/extra-addons
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/odoo.conf.template /etc/odoo/odoo.conf.template
COPY docker/init_masar.py /opt/masar/init_masar.py

RUN chmod +x /entrypoint.sh \
    && mkdir -p /var/lib/odoo/filestore /var/lib/odoo/sessions /var/log/odoo /opt/masar \
    && chown -R odoo:odoo /mnt/extra-addons /var/lib/odoo /var/log/odoo /etc/odoo /opt/masar /entrypoint.sh

# Official image already exposes 8069/8072 and sets USER odoo in its entrypoint;
# we replace the entrypoint with MASAR's Railway-aware bootstrap.
USER odoo

ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]
