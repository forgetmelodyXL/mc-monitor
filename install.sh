#!/usr/bin/env bash
set -e

# ============================================================
# MC Server Monitor - 一键安装脚本 (Linux)
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="${HOME}/mc-monitor"
REPO_URL="https://github.com/forgetmelodyXL/mc-monitor.git"
PREFER_DOCKER=true

print_banner() {
    echo -e "${CYAN}"
    echo "============================================================"
    echo "   MC Server Monitor - 一键安装"
    echo "============================================================"
    echo -e "${NC}"
}

print_step() {
    echo -e "${GREEN}[*]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[x]${NC} $1"
}

check_command() {
    command -v "$1" >/dev/null 2>&1
}

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="${ID}"
        OS_ID_LIKE="${ID_LIKE:-}"
    elif [ -f /etc/redhat-release ]; then
        OS_ID="rhel"
    else
        OS_ID="unknown"
    fi

    case "${OS_ID}" in
        ubuntu|debian|linuxmint|pop)
            echo "debian"
            ;;
        centos|rhel|fedora|rocky|almalinux|ol)
            echo "rhel"
            ;;
        arch|manjaro)
            echo "arch"
            ;;
        alpine)
            echo "alpine"
            ;;
        *)
            if echo "${OS_ID_LIKE}" | grep -q "debian"; then
                echo "debian"
            elif echo "${OS_ID_LIKE}" | grep -q "rhel\|fedora"; then
                echo "rhel"
            else
                echo "unknown"
            fi
            ;;
    esac
}

need_sudo() {
    [ "$(id -u)" -ne 0 ]
}

run_as_root() {
    if need_sudo; then
        sudo "$@"
    else
        "$@"
    fi
}

install_git() {
    if check_command git; then
        return 0
    fi

    print_step "安装 git..."
    local os_type
    os_type=$(detect_os)

    case "${os_type}" in
        debian)
            run_as_root apt-get update -qq
            run_as_root apt-get install -y -qq git
            ;;
        rhel)
            run_as_root yum install -y -q git 2>/dev/null || run_as_root dnf install -y -q git
            ;;
        arch)
            run_as_root pacman -Sy --noconfirm git
            ;;
        alpine)
            run_as_root apk add --no-cache git
            ;;
        *)
            print_error "无法自动安装 git，请手动安装后重试"
            return 1
            ;;
    esac
}

install_docker() {
    if check_command docker && docker compose version >/dev/null 2>&1; then
        return 0
    fi

    print_step "安装 Docker..."

    # 优先使用官方安装脚本
    if check_command curl; then
        if curl -fsSL https://get.docker.com | run_as_root sh; then
            # 启动 docker 服务
            if check_command systemctl; then
                run_as_root systemctl start docker 2>/dev/null || true
                run_as_root systemctl enable docker 2>/dev/null || true
            fi
            # 将当前用户加入 docker 组
            if need_sudo; then
                run_as_root usermod -aG docker "$USER" 2>/dev/null || true
            fi
            return 0
        fi
    fi

    # 备用：用系统包管理器安装
    local os_type
    os_type=$(detect_os)

    case "${os_type}" in
        debian)
            run_as_root apt-get update -qq
            run_as_root apt-get install -y -qq docker.io docker-compose-plugin
            ;;
        rhel)
            run_as_root yum install -y -q docker 2>/dev/null || run_as_root dnf install -y -q docker
            run_as_root systemctl start docker 2>/dev/null || true
            run_as_root systemctl enable docker 2>/dev/null || true
            ;;
        *)
            return 1
            ;;
    esac

    if check_command docker && docker compose version >/dev/null 2>&1; then
        return 0
    fi

    return 1
}

install_python3() {
    if check_command python3; then
        return 0
    fi

    print_step "安装 Python3..."
    local os_type
    os_type=$(detect_os)

    case "${os_type}" in
        debian)
            run_as_root apt-get update -qq
            run_as_root apt-get install -y -qq python3 python3-pip python3-venv
            ;;
        rhel)
            run_as_root yum install -y -q python3 python3-pip 2>/dev/null || \
            run_as_root dnf install -y -q python3 python3-pip
            ;;
        arch)
            run_as_root pacman -Sy --noconfirm python python-pip
            ;;
        alpine)
            run_as_root apk add --no-cache python3 py3-pip python3-venv
            ;;
        *)
            print_error "无法自动安装 Python3，请手动安装后重试"
            return 1
            ;;
    esac
}

gen_secret() {
    python3 -c "import secrets; print(secrets.token_hex(32))"
}

gen_password() {
    python3 -c "import secrets; print(secrets.token_urlsafe(12))"
}

detect_install_method() {
    if check_command docker && docker compose version >/dev/null 2>&1; then
        echo "docker"
    elif check_command python3; then
        echo "python"
    else
        echo ""
    fi
}

ensure_prerequisites() {
    install_git

    local method
    method=$(detect_install_method)

    if [ -n "${method}" ]; then
        return 0
    fi

    echo ""
    print_warn "服务器缺少 Docker 和 Python3"
    echo ""
    echo "  请选择安装方式："
    echo "    1) Docker (推荐，隔离性好)"
    echo "    2) Python3 (轻量，直接运行)"
    echo ""
    read -p "  请输入选项 [1/2] (默认 1): " choice
    choice="${choice:-1}"

    case "${choice}" in
        1|docker|Docker)
            print_step "正在安装 Docker，这可能需要几分钟..."
            if ! install_docker; then
                print_warn "Docker 安装失败，尝试安装 Python3..."
                install_python3
            fi
            ;;
        2|python|Python)
            install_python3
            ;;
        *)
            print_error "无效选项"
            exit 1
            ;;
    esac

    method=$(detect_install_method)
    if [ -z "${method}" ]; then
        print_error "自动安装依赖失败，请手动安装 Docker 或 Python3 后重试"
        exit 1
    fi
}

install_docker_method() {
    print_step "使用 Docker 方式安装"

    if [ ! -d "${INSTALL_DIR}" ]; then
        print_step "克隆代码仓库..."
        git clone "${REPO_URL}" "${INSTALL_DIR}"
    else
        print_warn "目录 ${INSTALL_DIR} 已存在，跳过克隆"
    fi

    cd "${INSTALL_DIR}"

    if [ ! -f ".env" ]; then
        print_step "生成配置文件..."
        SECRET_KEY=$(gen_secret)
        BOOTSTRAP_PASSWORD=$(gen_password)

        cat > .env <<EOF
MCMONITOR_ENV=production
MCMONITOR_SECRET_KEY=${SECRET_KEY}
MCMONITOR_HOST=0.0.0.0
MCMONITOR_PORT=5000
MCMONITOR_NOBROWSER=1
MCMONITOR_BOOTSTRAP_PASSWORD=${BOOTSTRAP_PASSWORD}
EOF
    else
        print_warn ".env 已存在，跳过配置生成"
        BOOTSTRAP_PASSWORD=$(grep -oP 'MCMONITOR_BOOTSTRAP_PASSWORD=\K.*' .env 2>/dev/null || echo "")
    fi

    print_step "构建并启动服务..."

    DOCKER_CMD="docker"
    if need_sudo && ! groups | grep -q "\bdocker\b"; then
        DOCKER_CMD="sudo docker"
        print_warn "当前用户不在 docker 组中，使用 sudo 运行 docker 命令"
    fi

    ${DOCKER_CMD} compose up -d --build

    ADMIN_PASSWORD="${BOOTSTRAP_PASSWORD}"
    IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "你的服务器IP")

    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "  ${GREEN}安装完成！${NC}"
    echo -e "${GREEN}============================================================${NC}"
    echo "  安装目录: ${INSTALL_DIR}"
    echo "  访问地址: http://${IP_ADDR}:5000"
    echo "  管理员账号: admin"
    if [ -n "${ADMIN_PASSWORD}" ]; then
        echo -e "  管理员密码: ${YELLOW}${ADMIN_PASSWORD}${NC}"
    else
        echo "  管理员密码: 请查看 .env 文件中的 MCMONITOR_BOOTSTRAP_PASSWORD"
    fi
    echo ""
    echo "  常用命令:"
    echo "    cd ${INSTALL_DIR}"
    echo "    ${DOCKER_CMD} compose logs -f    # 查看日志"
    echo "    ${DOCKER_CMD} compose stop       # 停止"
    echo "    ${DOCKER_CMD} compose start      # 启动"
    echo "    ${DOCKER_CMD} compose down       # 卸载（保留数据）"
    echo ""
    echo -e "${YELLOW}  ⚠️  首次登录后请及时修改管理员密码！${NC}"
    echo -e "${GREEN}============================================================${NC}"
}

install_python_method() {
    print_step "使用 Python 原生方式安装"

    if [ ! -d "${INSTALL_DIR}" ]; then
        print_step "克隆代码仓库..."
        git clone "${REPO_URL}" "${INSTALL_DIR}"
    else
        print_warn "目录 ${INSTALL_DIR} 已存在，跳过克隆"
    fi

    cd "${INSTALL_DIR}"

    # 确保 pip 和 venv 可用
    if ! python3 -m venv --help >/dev/null 2>&1; then
        print_warn "python3-venv 不可用，尝试安装..."
        local os_type
        os_type=$(detect_os)
        if [ "${os_type}" = "debian" ]; then
            run_as_root apt-get install -y -qq python3-venv
        fi
    fi

    print_step "创建虚拟环境..."
    python3 -m venv venv
    source venv/bin/activate

    print_step "安装依赖..."
    pip install --upgrade pip -q
    pip install -r requirements.txt -q

    if [ ! -f ".env" ]; then
        print_step "生成配置文件..."
        SECRET_KEY=$(gen_secret)
        BOOTSTRAP_PASSWORD=$(gen_password)

        cat > .env <<EOF
MCMONITOR_ENV=production
MCMONITOR_SECRET_KEY=${SECRET_KEY}
MCMONITOR_HOST=0.0.0.0
MCMONITOR_PORT=5000
MCMONITOR_NOBROWSER=1
MCMONITOR_BOOTSTRAP_PASSWORD=${BOOTSTRAP_PASSWORD}
EOF
    else
        print_warn ".env 已存在，跳过配置生成"
        BOOTSTRAP_PASSWORD=$(grep -oP 'MCMONITOR_BOOTSTRAP_PASSWORD=\K.*' .env 2>/dev/null || echo "")
    fi

    # 尝试配置 systemd 服务
    SYSTEMD_SETUP=false
    if check_command systemctl && [ "$(id -u)" -eq 0 ] || need_sudo; then
        echo ""
        read -p "  是否配置 systemd 后台服务（开机自启）？[Y/n]: " setup_systemd
        setup_systemd="${setup_systemd:-Y}"

        if [ "${setup_systemd}" = "Y" ] || [ "${setup_systemd}" = "y" ]; then
            print_step "配置 systemd 服务..."
            SERVICE_FILE="/etc/systemd/system/mc-monitor.service"
            run_as_root tee "${SERVICE_FILE}" > /dev/null <<EOF
[Unit]
Description=MC Server Monitor
After=network.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${INSTALL_DIR}
Environment="MCMONITOR_ENV=production"
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
            run_as_root systemctl daemon-reload
            run_as_root systemctl enable mc-monitor
            run_as_root systemctl start mc-monitor
            SYSTEMD_SETUP=true
        fi
    fi

    ADMIN_PASSWORD="${BOOTSTRAP_PASSWORD}"
    IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "你的服务器IP")

    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "  ${GREEN}安装完成！${NC}"
    echo -e "${GREEN}============================================================${NC}"
    echo "  安装目录: ${INSTALL_DIR}"
    echo "  访问地址: http://${IP_ADDR}:5000"
    echo "  管理员账号: admin"
    if [ -n "${ADMIN_PASSWORD}" ]; then
        echo -e "  管理员密码: ${YELLOW}${ADMIN_PASSWORD}${NC}"
    else
        echo "  管理员密码: 请查看 .env 文件中的 MCMONITOR_BOOTSTRAP_PASSWORD"
    fi
    echo ""
    if ${SYSTEMD_SETUP}; then
        echo "  服务已通过 systemd 启动："
        echo "    systemctl status mc-monitor   # 查看状态"
        echo "    systemctl restart mc-monitor  # 重启"
        echo "    systemctl stop mc-monitor     # 停止"
        echo "    journalctl -u mc-monitor -f   # 查看日志"
    else
        echo "  手动启动:"
        echo "    cd ${INSTALL_DIR}"
        echo "    source venv/bin/activate"
        echo "    set -a && source .env && set +a"
        echo "    python main.py"
    fi
    echo ""
    echo -e "${YELLOW}  ⚠️  首次登录后请及时修改管理员密码！${NC}"
    echo -e "${GREEN}============================================================${NC}"
}

# ============================================================
# 主流程
# ============================================================

print_banner

ensure_prerequisites

METHOD=$(detect_install_method)

if [ "${METHOD}" = "docker" ]; then
    install_docker_method
else
    install_python_method
fi
