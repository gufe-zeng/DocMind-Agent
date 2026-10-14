# M1b 网络排查：Windows Clash (7897) + Docker Desktop

## 已确认故障

文档上传请求返回 `201 Created`，但第一次执行
`POST /v1/documents/{id}/index` 返回 `503`。日志定位到
FastEmbed 初始化时调用 Hugging Face `model_info()`，出现：

- `No address associated with hostname`;
- `SSL: UNEXPECTED_EOF_WHILE_READING`.

这说明失败发生在**首次下载 Embedding 模型**，不是 PDF/DOCX
解析、PostgreSQL 健康检查或 Qdrant 健康检查。

用户在 Windows 主机运行 Clash，HTTP/mixed proxy 端口为 `7897`。
之前在 Windows Git 中设置的 `http.proxy` 不会自动传递给容器。

## 1. 容器如何访问 Windows 代理

```text
Windows programs → 127.0.0.1:7897
Docker API container → host.docker.internal:7897
```

容器内部的 `127.0.0.1` 不是 Windows 宿主机。

项目提供了可选的 `compose.proxy.yaml`，仅为 `api` 服务设置
HTTP(S) proxy 和 NO_PROXY。PostgreSQL、Redis、Qdrant 服务不使用代理。

需要注意：Clash 监听 Windows 回环地址时，容器访问
`host.docker.internal:7897` 仍可能被拒绝。只有在确认这一点后，
才考虑开启 Clash 的 Allow LAN / 允许局域网访问。开启后要通过
防火墙保护代理端口，不要把未鉴权代理公开到不可信局域网。

## 2. 使用 Clash 代理重建 API 容器

在 Windows CMD 中：

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose -f compose.yaml -f compose.proxy.yaml config
docker compose -f compose.yaml -f compose.proxy.yaml up -d --no-deps --force-recreate api
```

这里 **不需要** `--build`，因为本次只改变 API 容器的环境变量；
数据库和 Qdrant 数据卷保持不变。

检查配置是否进入容器：

```cmd
docker compose exec -T api python -c "import os; print(os.getenv('HTTPS_PROXY')); print(os.getenv('HF_ENDPOINT')); print(os.getenv('NO_PROXY'))"
```

应该能看到：

```text
http://host.docker.internal:7897
https://huggingface.co
localhost,127.0.0.1,...postgres,redis,qdrant,...
```

`HF_ENDPOINT` 也可以通过 .env 设置为 `https://hf-mirror.com`，
但能访问镜像站首页不代表具体模型的元数据和文件可以成功下载。

## 3. 测试模型元数据，而不是测试首页

```cmd
docker compose exec -T api python -c "import os,httpx; u=os.getenv('HF_ENDPOINT','https://huggingface.co').rstrip('/')+'/api/models/BAAI/bge-small-zh-v1.5'; r=httpx.get(u,timeout=30); print(u,r.status_code); r.raise_for_status()"
```

成功返回 HTTP 200 表示模型元数据接口可达，但不能单独证明
所有模型权重文件也可达。

如果错误为 `ConnectError` 或 `Connection refused`，
检查 Clash 是否允许容器访问端口 `7897`。

如果出现 `SSL` 或 `ReadTimeout` 错误，
检查 Clash 节点、规则及针对 Hugging Face / CDN 的代理路径。

查看 FastEmbed 实际所需的模型源：

```cmd
docker compose exec -T api python -c "from fastembed import TextEmbedding; print([x for x in TextEmbedding.list_supported_models() if x['model']=='BAAI/bge-small-zh-v1.5'])"
```

## 4. 重试 M1b

```cmd
scripts\check_m1b.bat
```

脚本会重新上传合成测试文档、索引并校验 512 维向量与来源信息。

成功标准：

```text
PASS sample_contract.txt
PASS idempotent reindex
PASS synthetic.pdf
PASS synthetic.docx
M1b PASS
```

出现 503 后不要反复 `docker compose up --build`；如果是模型下载网络错误，
重复镜像构建不会修复 HTTPS 连接。优先查看：

```cmd
docker compose logs --tail 80 api
```

## 5. 数据安全与后续启动

- 保留 Docker volumes：`postgres-data`、`redis-data`、
  `qdrant-data`、`documents-data`、`embedding-cache`。
- 不要运行 `docker compose down -v`。
- 若需要在后续重建 API 容器时继续使用代理，要同样提供两个
  `-f` 配置文件。普通 `docker compose up` 不会自动加载
  `compose.proxy.yaml`。
- 首次模型完整缓存后，推理和本地文档索引一般不需要持续联网。
