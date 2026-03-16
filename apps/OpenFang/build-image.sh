#!/bin/bash
# 构建 OpenFang 自定义镜像

IMAGE_NAME="registry.lazycat.cloud/invokerlaw/codeeagle/openfang"
IMAGE_TAG=$(git rev-parse --short HEAD)

echo "Building OpenFang custom image..."
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"

# 构建镜像
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

# 推送到懒猫微服镜像仓库
docker push ${IMAGE_NAME}:${IMAGE_TAG}

echo ""
echo "Build complete!"
echo "Update lzc-manifest.yml image field to: ${IMAGE_NAME}:${IMAGE_TAG}"
