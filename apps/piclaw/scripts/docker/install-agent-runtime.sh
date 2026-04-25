#!/usr/bin/env bash
# LazyCat overlay for Piclaw's upstream runtime installer.
#
# Upstream installs GitHub CLI through Linux Homebrew. Local amd64 Docker
# builds under Colima can expose a CPU without SSSE3, which Homebrew rejects
# before Bun/Piclaw are installed. This keeps the runtime contents equivalent
# for the app by installing Bun, pi-coding-agent, and gh directly.
set -euo pipefail

GH_CLI_VERSION="${GH_CLI_VERSION:-2.91.0}"

resolve_bun_platform() {
  local raw_arch="${BUN_ARCH:-${TARGETARCH:-$(uname -m)}}"
  case "$raw_arch" in
    amd64|x86_64)
      echo "linux-x64"
      ;;
    arm64|aarch64)
      echo "linux-aarch64"
      ;;
    armv7l|armv7)
      echo "linux-armv7l"
      ;;
    *)
      echo "linux-$raw_arch"
      ;;
  esac
}

supports_avx2() {
  grep -qi 'avx2' /proc/cpuinfo
}

resolve_bun_version() {
  local bun_version="${BUN_VERSION:-}"

  if [ -z "$bun_version" ]; then
    for version_file in /tmp/BUN_VERSION "$HOME/piclaw/BUN_VERSION"; do
      if [ -f "$version_file" ]; then
        bun_version="$(tr -d '[:space:]' < "$version_file")"
        [ -n "$bun_version" ] && break
      fi
    done
  fi

  bun_version="${bun_version#v}"
  bun_version="${bun_version#bun-v}"

  if [ -n "$bun_version" ]; then
    echo "$bun_version"
    return 0
  fi

  echo "BUN_VERSION is not set and no pinned BUN_VERSION file was found." >&2
  return 1
}

install_bun_release() (
  bun_version="$1"
  bun_target="$2"
  temp_dir="$(mktemp -d)"
  trap 'rm -rf "$temp_dir"' EXIT

  filename="bun-${bun_target}.zip"
  base_url="https://github.com/oven-sh/bun/releases/download/bun-v${bun_version}"
  url="${base_url}/${filename}"
  bundle="$temp_dir/$filename"
  checksums="$temp_dir/SHASUMS256.txt"

  curl -fsSL --fail "$url" -o "$bundle"
  curl -fsSL --fail "${base_url}/SHASUMS256.txt" -o "$checksums"

  expected_checksum=$(awk -v name="$filename" '$2 == name { print $1; exit }' "$checksums")
  if [ -z "$expected_checksum" ]; then
    echo "Missing checksum entry for $filename in SHASUMS256.txt" >&2
    return 1
  fi

  actual_checksum=$(sha256sum "$bundle" | awk '{print $1}')
  if [ "$actual_checksum" != "$expected_checksum" ]; then
    echo "Checksum mismatch for $filename" >&2
    echo "Expected: $expected_checksum" >&2
    echo "Actual:   $actual_checksum" >&2
    return 1
  fi

  unzip -q "$bundle" -d "$temp_dir/extract"

  bun_binary=""
  for candidate in "$temp_dir/extract/bun-${bun_target}/bun" "$temp_dir/extract/${bun_target}/bun"; do
    if [ -f "$candidate" ]; then
      bun_binary="$candidate"
      break
    fi
  done

  if [ -z "$bun_binary" ]; then
    echo "Unexpected Bun archive layout for $bun_target" >&2
    ls -la "$temp_dir/extract/" >&2
    return 1
  fi

  sudo mkdir -p "$BUN_INSTALL/bin"
  sudo cp "$bun_binary" "$BUN_INSTALL/bin/bun"
  sudo chmod 755 "$BUN_INSTALL/bin/bun"
)

install_bun() {
  local bun_platform
  local bun_version
  local bun_prefer_baseline="${BUN_PREFER_BASELINE:-auto}"
  local -a candidates

  bun_platform=$(resolve_bun_platform)
  bun_version=$(resolve_bun_version)

  if [ "$bun_platform" = "linux-x64" ]; then
    case "$bun_prefer_baseline" in
      always|true|1)
        candidates=("linux-x64-baseline")
        ;;
      never|false|0)
        candidates=("linux-x64")
        ;;
      *)
        if supports_avx2; then
          candidates=("linux-x64" "linux-x64-baseline")
        else
          candidates=("linux-x64-baseline")
        fi
        ;;
    esac
  else
    candidates=("$bun_platform")
  fi

  for bun_target in "${candidates[@]}"; do
    if install_bun_release "$bun_version" "$bun_target"; then
      if "$BUN_INSTALL/bin/bun" --version >/dev/null 2>&1; then
        return 0
      fi
      echo "Installed Bun ${bun_target} failed validation; trying next candidate" >&2
    fi
  done

  echo "Could not install a compatible Bun binary for platform '$bun_platform' (version '$bun_version')." >&2
  return 1
}

install_gh_release() (
  gh_version="${GH_CLI_VERSION#v}"
  raw_arch="${TARGETARCH:-$(uname -m)}"
  case "$raw_arch" in
    amd64|x86_64)
      gh_arch="amd64"
      ;;
    arm64|aarch64)
      gh_arch="arm64"
      ;;
    armv6|armv6l)
      gh_arch="armv6"
      ;;
    armv7|armv7l)
      gh_arch="armv6"
      ;;
    386|i386|i686)
      gh_arch="386"
      ;;
    *)
      echo "Unsupported gh architecture: $raw_arch" >&2
      return 1
      ;;
  esac

  temp_dir="$(mktemp -d)"
  trap 'rm -rf "$temp_dir"' EXIT

  filename="gh_${gh_version}_linux_${gh_arch}.tar.gz"
  base_url="https://github.com/cli/cli/releases/download/v${gh_version}"
  archive="$temp_dir/$filename"
  checksums="$temp_dir/checksums.txt"

  curl -fsSL --fail "${base_url}/${filename}" -o "$archive"
  curl -fsSL --fail "${base_url}/gh_${gh_version}_checksums.txt" -o "$checksums"

  expected_checksum=$(awk -v name="$filename" '$2 == name { print $1; exit }' "$checksums")
  if [ -z "$expected_checksum" ]; then
    echo "Missing checksum entry for $filename" >&2
    return 1
  fi

  actual_checksum=$(sha256sum "$archive" | awk '{print $1}')
  if [ "$actual_checksum" != "$expected_checksum" ]; then
    echo "Checksum mismatch for $filename" >&2
    echo "Expected: $expected_checksum" >&2
    echo "Actual:   $actual_checksum" >&2
    return 1
  fi

  tar -xzf "$archive" -C "$temp_dir"
  gh_binary="$(find "$temp_dir" -path '*/bin/gh' -type f | head -n1)"
  if [ -z "$gh_binary" ]; then
    echo "Unexpected gh archive layout for $filename" >&2
    find "$temp_dir" -maxdepth 3 -type f >&2
    return 1
  fi

  sudo mkdir -p /home/linuxbrew/.linuxbrew/bin
  sudo install -m 0755 "$gh_binary" /home/linuxbrew/.linuxbrew/bin/gh
  sudo chown -R agent:agent /home/linuxbrew
)

export BUN_INSTALL="/usr/local/lib/bun"
export BUN_INSTALL_CACHE_DIR="/tmp/bun-cache"
sudo mkdir -p "$BUN_INSTALL" "$BUN_INSTALL_CACHE_DIR"

install_bun
sudo chmod -R a+rX "$BUN_INSTALL"

sudo ln -sf "$BUN_INSTALL/bin/bun" /usr/local/bin/bun
if [ -f "$BUN_INSTALL/bin/bunx" ]; then
  sudo ln -sf "$BUN_INSTALL/bin/bunx" /usr/local/bin/bunx
else
  sudo ln -sf "$BUN_INSTALL/bin/bun" /usr/local/bin/bunx
fi

PI_CODING_AGENT_VERSION="${PI_CODING_AGENT_VERSION:-}"
if [ -z "$PI_CODING_AGENT_VERSION" ]; then
  for pkg in /tmp/piclaw-package.json "$HOME/piclaw/package.json"; do
    if [ -f "$pkg" ]; then
      PI_CODING_AGENT_VERSION="$(jq -r '.dependencies["@mariozechner/pi-coding-agent"] // empty' "$pkg")"
      [ -n "$PI_CODING_AGENT_VERSION" ] && break
    fi
  done
fi
PI_CODING_AGENT_VERSION="${PI_CODING_AGENT_VERSION:-0.58.3}"
sudo BUN_INSTALL="$BUN_INSTALL" BUN_INSTALL_CACHE_DIR="$BUN_INSTALL_CACHE_DIR" "$BUN_INSTALL/bin/bun" add -g "@mariozechner/pi-coding-agent@${PI_CODING_AGENT_VERSION}"

sudo chmod -R a+rX "$BUN_INSTALL"
sudo ln -sf "$BUN_INSTALL/bin/pi" /usr/local/bin/pi

PI_CLI="$(readlink -f "$BUN_INSTALL/bin/pi")"
if [ -f "$PI_CLI" ] && head -n1 "$PI_CLI" | grep -q 'env node'; then
  sudo sed -i '1s/env node/env bun/' "$PI_CLI"
fi
sudo chmod +x "$PI_CLI"

install_gh_release

rm -rf "$HOME/.cache" "$HOME/.bun"
rm -rf /home/linuxbrew/.cache 2>/dev/null || true
sudo rm -rf "$BUN_INSTALL_CACHE_DIR" "$BUN_INSTALL/install/cache"
