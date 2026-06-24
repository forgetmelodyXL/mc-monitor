#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="${HOME}/mc-monitor"

echo -e "${CYAN}"
echo "============================================================"
echo "   MC Server Monitor - 更新"
echo "============================================================"
echo -e "${NC}"

if [ ! -d "${INSTALL_DIR}" ]; then
    echo "未找到安装目录: ${INSTALL_DIR}"
    exit 1
fi

cd "${INSTALL_DIR}"

need_sudo() {
    [ "$(id -u)" -ne 0 ]
}

echo ""
echo -e "${GREEN}[*]${NC} 拉取最新代码..."
git pull

DOCKER_CMD="docker"
if command -v docker >/dev/null 2>&1 && [ -f "docker-compose.yml" ]; then
    if need_sudo && ! groups | grep -q "\bdocker\b"; then
        DOCKER_CMD="sudo docker"
    fi

    if ${DOCKER_CMD} compose ps --quiet 2>/dev/null | grep -q .; then
        echo ""
        echo -e "${GREEN}[*]${NC} 重新构建并启动 Docker 容器..."
        ${DOCKER_CMD} compose up -d --build
        echo ""
        echo -e "${GREEN}更新完成！服务已重启。${NC}"
        echo "  查看日志: ${DOCKER_CMD} compose logs -f"
        echo ""
        exit 0
    fi
fi

if [ -d "venv" ]; then
    echo ""
    echo -e "${GREEN}[*]${NC} 更新 Python 依赖..."
    source venv/bin/activate
    pip install -r requirements.txt -q

    if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q mc-monitor.service; then
        echo ""
        echo -e "${GREEN}[*]${NC} 重启 systemd 服务..."
        if need_sudo; then
            sudo systemctl restart mc-monitor
        else
            systemctl restart mc-monitor
        fi
        echo ""
        echo -e "${GREEN}更新完成！服务已重启。${NC}"
        echo "  查看日志: journalctl -u mc-monitor -f"
    else
        echo ""
        echo -e "${YELLOW}更新完成！请手动重启服务。${NC}"
    fi
    echo ""
    exit 0
fi

echo ""
echo -e "${YELLOW}代码已更新，请手动重启服务。${NC}"
echo ""
