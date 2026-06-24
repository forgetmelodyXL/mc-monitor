#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="${HOME}/mc-monitor"

echo -e "${RED}"
echo "============================================================"
echo "   MC Server Monitor - 卸载"
echo "============================================================"
echo -e "${NC}"

if [ ! -d "${INSTALL_DIR}" ]; then
    echo "未找到安装目录: ${INSTALL_DIR}"
    exit 0
fi

need_sudo() {
    [ "$(id -u)" -ne 0 ]
}

echo ""
echo -e "${YELLOW}  安装目录: ${INSTALL_DIR}${NC}"
read -p "  确定要卸载吗？数据会保留在 data/ 目录 (y/N): " confirm

if [ "${confirm}" != "y" ] && [ "${confirm}" != "Y" ]; then
    echo "已取消"
    exit 0
fi

cd "${INSTALL_DIR}"

DOCKER_CMD="docker"
if command -v docker >/dev/null 2>&1 && [ -f "docker-compose.yml" ]; then
    if need_sudo && ! groups | grep -q "\bdocker\b"; then
        DOCKER_CMD="sudo docker"
    fi

    echo ""
    echo -e "${GREEN}[*]${NC} 停止 Docker 容器..."
    ${DOCKER_CMD} compose down 2>/dev/null || true
fi

# 停止 systemd 服务
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q mc-monitor.service; then
    echo ""
    echo -e "${GREEN}[*]${NC} 停止并禁用 systemd 服务..."
    if need_sudo; then
        sudo systemctl stop mc-monitor 2>/dev/null || true
        sudo systemctl disable mc-monitor 2>/dev/null || true
        sudo rm -f /etc/systemd/system/mc-monitor.service
        sudo systemctl daemon-reload
    else
        systemctl stop mc-monitor 2>/dev/null || true
        systemctl disable mc-monitor 2>/dev/null || true
        rm -f /etc/systemd/system/mc-monitor.service
        systemctl daemon-reload
    fi
fi

echo ""
echo -e "${GREEN}[*]${NC} 删除安装目录 (保留 data/)..."

if [ -d "data" ]; then
    TMP_DATA=$(mktemp -d)
    mv data "${TMP_DATA}/data"
    rm -rf "${INSTALL_DIR}"
    mkdir -p "${INSTALL_DIR}"
    mv "${TMP_DATA}/data" "${INSTALL_DIR}/data"
    rm -rf "${TMP_DATA}"
    echo "  数据已保留在: ${INSTALL_DIR}/data"
else
    rm -rf "${INSTALL_DIR}"
fi

echo ""
echo -e "${GREEN}卸载完成！${NC}"
echo ""
