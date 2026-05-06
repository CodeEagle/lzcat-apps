#!/bin/sh
set -eu

mkdir -p \
  /opt/memoh/data \
  /var/lib/cni \
  /var/lib/containerd \
  /run/containerd

sh /lzcapp/pkg/content/render-config.sh /app/config.toml

ip link delete cni0 2>/dev/null || true
rm -rf /var/lib/cni/networks/* /var/lib/cni/results/* 2>/dev/null || true
sysctl -w net.ipv4.ip_forward=1 2>/dev/null || true
iptables -t nat -C POSTROUTING -s 10.88.0.0/16 ! -o cni0 -j MASQUERADE 2>/dev/null \
  || iptables -t nat -A POSTROUTING -s 10.88.0.0/16 ! -o cni0 -j MASQUERADE 2>/dev/null \
  || true

if [ -f /sys/fs/cgroup/cgroup.controllers ] && [ -w /sys/fs/cgroup ]; then
  mkdir -p /sys/fs/cgroup/init 2>/dev/null || true
  if [ -d /sys/fs/cgroup/init ]; then
    while read -r pid; do
      echo "${pid}" > /sys/fs/cgroup/init/cgroup.procs 2>/dev/null || true
    done < /sys/fs/cgroup/cgroup.procs
  fi
  sed -e 's/ / +/g' -e 's/^/+/' < /sys/fs/cgroup/cgroup.controllers > /sys/fs/cgroup/cgroup.subtree_control 2>/dev/null || true
else
  echo "[memoh] skip cgroup v2 delegation: /sys/fs/cgroup is not writable"
fi

containerd &
CONTAINERD_PID=$!

for i in $(seq 1 30); do
  if ctr version >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! ctr version >/dev/null 2>&1; then
  echo "ERROR: containerd not responsive after 30s"
  exit 1
fi

cleanup() {
  kill "${SERVER_PID:-}" 2>/dev/null || true
  kill "${CONTAINERD_PID}" 2>/dev/null || true
  wait
}

trap cleanup TERM INT

/app/memoh-server serve &
SERVER_PID=$!
wait "${SERVER_PID}"
EXIT_CODE=$?

kill "${CONTAINERD_PID}" 2>/dev/null || true
wait "${CONTAINERD_PID}" 2>/dev/null || true
exit "${EXIT_CODE}"
