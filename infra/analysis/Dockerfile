# This image deliberately contains no Lonora package, broker SDK or credentials.
# Update the pinned upstream image through review; execution uses the local ID.
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
ENV HOME=/work PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
WORKDIR /work
ENTRYPOINT ["/bin/sleep"]
CMD ["120"]
