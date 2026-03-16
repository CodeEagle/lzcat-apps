#!/bin/bash
set -e

# 检查是否配置了 LLM API Key
check_api_keys() {
    local keys=(
        "ANTHROPIC_API_KEY"
        "OPENAI_API_KEY"
        "GEMINI_API_KEY"
        "GOOGLE_API_KEY"
        "GROQ_API_KEY"
        "DEEPSEEK_API_KEY"
        "OPENROUTER_API_KEY"
        "TOGETHER_API_KEY"
        "MISTRAL_API_KEY"
        "FIREWORKS_API_KEY"
    )

    for key in "${keys[@]}"; do
        if [ -n "${!key}" ]; then
            echo "✓ Found API key: $key"
            return 0
        fi
    done

    # 检查本地 LLM 配置
    if [ -n "$OLLAMA_BASE_URL" ] || [ -n "$VLLM_BASE_URL" ] || [ -n "$LMSTUDIO_BASE_URL" ]; then
        echo "✓ Found local LLM configuration"
        return 0
    fi

    return 1
}

# 启动配置引导页面
start_setup_page() {
    echo "=============================================="
    echo "⚠️  No LLM API Key configured!"
    echo "📋 Starting setup guide page on port 4200..."
    echo "=============================================="

    cd /opt/openfang/setup

    # busybox-static 安装在 /bin/busybox
    if [ -x /bin/busybox ]; then
        echo "Starting HTTP server with busybox..."
        exec /bin/busybox httpd -f -p 4200 -h .
    elif command -v busybox &> /dev/null; then
        echo "Starting HTTP server with busybox..."
        exec busybox httpd -f -p 4200 -h .
    else
        echo "ERROR: No HTTP server available!"
        echo "Please configure LLM API Key in environment variables:"
        echo "  - ANTHROPIC_API_KEY"
        echo "  - OPENAI_API_KEY"
        echo "  - GEMINI_API_KEY"
        echo "  - etc."
        # 保持容器运行
        while true; do
            sleep 3600
        done
    fi
}

# 主逻辑
echo "=============================================="
echo "🔍 Checking LLM API Key configuration..."
echo "=============================================="

if check_api_keys; then
    echo "=============================================="
    echo "✅ API Key configured, starting OpenFang..."
    echo "=============================================="
    exec openfang start
else
    start_setup_page
fi
