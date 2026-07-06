FROM debian:13
ENV container=docker DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus python3 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
# Units that fail or are pointless inside a container
RUN systemctl mask systemd-udevd.service systemd-udevd-kernel.socket \
      systemd-udevd-control.socket systemd-networkd.service \
      systemd-resolved.service getty@tty1.service
STOPSIGNAL SIGRTMIN+3
CMD ["/lib/systemd/systemd"]
