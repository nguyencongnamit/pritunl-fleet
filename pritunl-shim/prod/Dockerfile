# Production shim — built FROM the node's Pritunl image so it shares Pritunl's
# exact Python modules + version. Build context = pritunl-shim/.
#
# Swap the base to match your node's Pritunl image/version:
ARG PRITUNL_IMAGE=goofball222/pritunl:latest
FROM ${PRITUNL_IMAGE}

# Shared HMAC module + the shim app (no extra deps — uses the image's Flask).
COPY shim/ /shim/shim/
COPY prod/shim_app.py /shim/shim_app.py
COPY prod/entrypoint.sh /usr/local/bin/shim-entrypoint.sh
RUN chmod +x /usr/local/bin/shim-entrypoint.sh

ENV PYTHONPATH=/shim
EXPOSE 9800
ENTRYPOINT ["/usr/local/bin/shim-entrypoint.sh"]
