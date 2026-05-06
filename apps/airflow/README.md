# Apache Airflow

Apache Airflow 是一个开源的工作流管理平台，用于开发、调度和监控批处理工作流。

## 上游项目

- **项目地址**: https://github.com/apache/airflow
- **官方文档**: https://airflow.apache.org/docs/
- **Docker Hub**: https://hub.docker.com/r/apache/airflow

## 应用说明

本应用采用 CeleryExecutor 模式部署，包含以下服务：

- **airflow-api-server**: Web UI 和 REST API 入口 (端口 8080)
- **airflow-scheduler**: 任务调度器
- **airflow-worker**: Celery 任务执行器
- **postgres**: PostgreSQL 元数据数据库
- **redis**: Redis 消息队列

## 访问方式

安装后通过 `https://airflow.你的域名` 访问 Web UI。

**默认登录账号**: `airflow`
**默认登录密码**: `airflow`

> 建议首次登录后立即修改密码

## 环境变量

### 必须配置

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `AIRFLOW__CORE__FERNET_KEY` | 用于加密连接密码的密钥 | 运行 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 生成 |
| `AIRFLOW__WEBSERVER__SECRET_KEY` | Web 服务器密钥 | 随机字符串 |

### 可选配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `AIRFLOW__CORE__LOAD_EXAMPLES` | 是否加载示例 DAG | False |

## 数据目录

| 路径 | 说明 |
|------|------|
| `/lzcapp/var/data/airflow/dags` | DAG 文件目录 |
| `/lzcapp/var/data/airflow/logs` | 日志目录 |
| `/lzcapp/var/data/airflow/plugins` | 自定义插件目录 |
| `/lzcapp/var/data/airflow/config` | 配置文件目录 |
| `/lzcapp/var/db/airflow/postgres` | PostgreSQL 数据库 |
| `/lzcapp/var/data/airflow/redis` | Redis 数据 |

## 首次启动

首次启动可能需要等待几分钟，系统会自动：
1. 初始化 PostgreSQL 数据库
2. 创建 Airflow 元数据表
3. 启动所有服务

## 添加 DAG

将 DAG 文件 (`.py`) 放入 `/lzcapp/var/data/airflow/dags` 目录即可自动被识别。

## 注意事项

- 本部署使用 CeleryExecutor，适合生产环境
- 建议配置足够的内存 (至少 4GB)
- 请妥善保管 `FERNET_KEY`，丢失后将无法解密已存储的连接密码
