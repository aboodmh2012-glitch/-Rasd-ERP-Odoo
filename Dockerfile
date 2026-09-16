# MASAR — Odoo 19 for Railway
FROM python:3.12-slim-bookworm

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    ODOO_RC=/etc/odoo/odoo.conf \
    ODOO_DATA_DIR=/var/lib/odoo \
    ODOO_HOME=/opt/odoo

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        fonts-dejavu-core \
        fonts-liberation \
        fonts-noto-core \
        fonts-noto-ui-core \
        libffi-dev \
        libfreetype6-dev \
        libjpeg62-turbo-dev \
        libldap2-dev \
        libopenjp2-7-dev \
        libpq-dev \
        libsasl2-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        libzip-dev \
        node-less \
        npm \
        postgresql-client \
        rtlcss \
        xz-utils \
        zlib1g-dev \
    && (curl -fsSL -o /tmp/wkhtmltox.deb \
        https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_amd64.deb \
        && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
        && rm -f /tmp/wkhtmltox.deb || echo "wkhtmltopdf optional install skipped") \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r odoo && useradd -r -g odoo -d ${ODOO_DATA_DIR} -s /bin/bash odoo \
    && mkdir -p /etc/odoo ${ODOO_DATA_DIR}/filestore ${ODOO_DATA_DIR}/sessions /var/log/odoo \
    && chown -R odoo:odoo ${ODOO_DATA_DIR} /var/log/odoo /etc/odoo

WORKDIR ${ODOO_HOME}

# Install Python deps first for better layer caching
COPY requirements.txt ${ODOO_HOME}/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

# Application source (Odoo core + addons + custom_addons)
COPY --chown=odoo:odoo . ${ODOO_HOME}

COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/odoo.conf.template /etc/odoo/odoo.conf.template
COPY docker/init_masar.py /opt/odoo/docker/init_masar.py
RUN chmod +x /entrypoint.sh \
    && chown -R odoo:odoo ${ODOO_HOME} /etc/odoo

EXPOSE 8069 8072

VOLUME ["/var/lib/odoo"]

USER odoo
ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]
