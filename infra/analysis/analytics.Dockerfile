# No application packages, broker SDK, credentials or project checkout.
# The wheel bundle is prepared by build-analytics.sh, verified against the lock.
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
COPY analytics.requirements.lock /opt/lonora-analysis/requirements.lock
COPY wheels /tmp/wheels
RUN python -c 'import platform,sys; assert sys.version_info[:2]==(3,12) and platform.machine()=="x86_64"' \
    && python -m pip install --no-cache-dir --no-index --find-links=/tmp/wheels \
       --require-hashes --only-binary=:all: --no-deps -r /opt/lonora-analysis/requirements.lock \
    && python -m pip check \
    && rm -rf /tmp/wheels
ENV HOME=/work PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
WORKDIR /work
ENTRYPOINT ["/bin/sleep"]
CMD ["120"]
