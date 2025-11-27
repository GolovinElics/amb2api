#!/bin/bash
# AMB2API 发布脚本
# 
# 功能：
#   1. 自动从 pyproject.toml 读取版本号
#   2. 检查是否有未提交的更改
#   3. 推送代码到 Git 仓库
#   4. 创建并推送 Git 标签（如 v0.3.0）
#   5. 构建多架构 Docker 镜像（linux/amd64 和 linux/arm64）
#   6. 推送镜像到 Docker Hub（带版本号和 latest 标签）
#
# 使用方法：
#   ./release.sh
#
# 发布新版本流程：
#   1. 更新 pyproject.toml 和 web.py 中的版本号
#   2. 提交更改：git commit -am "chore: bump version to x.x.x"
#   3. 运行此脚本：./release.sh
#
# 前置要求：
#   - 已登录 Docker Hub：docker login
#   - Docker buildx 已安装并可用
#   - 有 Git 仓库推送权限
#
set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 从 pyproject.toml 读取版本号
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')

if [ -z "$VERSION" ]; then
    echo -e "${RED}错误: 无法从 pyproject.toml 读取版本号${NC}"
    exit 1
fi

echo -e "${GREEN}=== AMB2API 发布脚本 ===${NC}"
echo -e "${YELLOW}当前版本: ${VERSION}${NC}"
echo ""

# 检查是否有未提交的更改
if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}错误: 有未提交的更改，请先提交或暂存${NC}"
    git status --short
    exit 1
fi

# 确认发布
echo -e "${YELLOW}即将执行以下操作:${NC}"
echo "1. 推送代码到 Git 仓库"
echo "2. 创建 Git 标签 v${VERSION}"
echo "3. 构建多架构 Docker 镜像 (linux/amd64, linux/arm64)"
echo "4. 推送镜像到 Docker Hub (golovin0623/amb2api:${VERSION} 和 latest)"
echo ""
read -p "确认继续? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}已取消${NC}"
    exit 0
fi

# 1. 推送代码到 Git
echo -e "${GREEN}[1/4] 推送代码到 Git...${NC}"
git push origin main

# 2. 创建并推送标签
echo -e "${GREEN}[2/4] 创建 Git 标签 v${VERSION}...${NC}"
if git rev-parse "v${VERSION}" >/dev/null 2>&1; then
    echo -e "${YELLOW}标签 v${VERSION} 已存在，跳过创建${NC}"
else
    git tag -a "v${VERSION}" -m "Release version ${VERSION}"
    git push origin "v${VERSION}"
fi

# 3. 检查 Docker buildx
echo -e "${GREEN}[3/4] 检查 Docker buildx...${NC}"
if ! docker buildx version >/dev/null 2>&1; then
    echo -e "${RED}错误: Docker buildx 不可用${NC}"
    exit 1
fi

# 确保 buildx builder 存在
if ! docker buildx inspect multiarch-builder >/dev/null 2>&1; then
    echo -e "${YELLOW}创建 buildx builder...${NC}"
    docker buildx create --name multiarch-builder --use
else
    docker buildx use multiarch-builder
fi

# 4. 构建并推送多架构镜像
echo -e "${GREEN}[4/4] 构建并推送 Docker 镜像...${NC}"
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    -t golovin0623/amb2api:${VERSION} \
    -t golovin0623/amb2api:latest \
    --push \
    .

echo ""
echo -e "${GREEN}=== 发布完成! ===${NC}"
echo -e "${GREEN}版本: ${VERSION}${NC}"
echo -e "${GREEN}镜像标签:${NC}"
echo "  - golovin0623/amb2api:${VERSION}"
echo "  - golovin0623/amb2api:latest"
echo ""
echo -e "${YELLOW}验证镜像:${NC}"
echo "  docker buildx imagetools inspect golovin0623/amb2api:${VERSION}"
echo ""
echo -e "${YELLOW}使用新版本:${NC}"
echo "  docker pull golovin0623/amb2api:${VERSION}"
echo "  docker compose down && docker compose up -d"
