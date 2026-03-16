# OpenFang 自定义镜像
# 巻加懒猫微服定制配置

FROM debian:bookworm-slim

# 安装 Hands 所需的依赖
# - ffmpeg, ffprobe, yt-dlp: Clip Hand 视频处理
# - python3, selenium, chromium: Browser Headless 浏览器自动化
RUN apt-get update && apt-get install -y --no-install-recommends \
    busybox-static \
    # Clip Hand 依赖
    ffmpeg \
    # Browser Hand 依赖
    python3 \
    python3-pip \
    python3-venv \
    chromium \
    chromium-driver \
    # Chromium 运行所需的系统库
    fonts-liberation \
    fonts-noto-cjk \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && pip3 install --no-cache-dir --break-system-packages \
    yt-dlp \
    selenium \
    && rm -rf /var/lib/apt/lists/* /root/.cache/pip

# 设置 Chromium 路径环境变量 (无头模式)
ENV CHROMIUM_BIN=/usr/bin/chromium
ENV CHROMIUM_FLAGS="--no-sandbox --disable-gpu --disable-dev-shm-usage"

# 复制二进制
COPY openfang /usr/local/bin/openfang
RUN chmod +x /usr/local/bin/openfang

# 复制 setup 目录
COPY setup /opt/openfang/setup

# 确保脚本可执行
RUN chmod +x /opt/openfang/setup/entrypoint.sh

EXPOSE 4200

CMD ["/opt/openfang/setup/entrypoint.sh"]
