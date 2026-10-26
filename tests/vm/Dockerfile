FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates python3 python3-paramiko python3-zeroconf \
    qemu-system-x86 qemu-utils ovmf mtools dosfstools openssh-client \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 1000 --create-home --shell /bin/bash runner
USER runner
WORKDIR /src
ENTRYPOINT ["python3", "tests/vm/run.py"]
