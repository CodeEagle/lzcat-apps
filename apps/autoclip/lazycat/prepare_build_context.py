from pathlib import Path
import sys


def patch_frontend(frontend_root: Path) -> None:
    replacements = {
        "http://localhost:8000/api/v1": "/api/v1",
        "http://127.0.0.1:8000/api/v1": "/api/v1",
        "http://localhost:8000/api": "/api",
        "http://127.0.0.1:8000/api": "/api",
    }

    for path in frontend_root.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        text = path.read_text()
        updated = text
        for source, target in replacements.items():
            updated = updated.replace(source, target)
        updated = updated.replace(
            "`ws://localhost:8000/api/v1/ws/${userId}`",
            "`${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/v1/ws/${userId}`",
        )
        updated = updated.replace(
            "`ws://127.0.0.1:8000/api/v1/ws/${userId}`",
            "`${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/v1/ws/${userId}`",
        )
        if updated != text:
            path.write_text(updated)


def patch_task_utils(backend_root: Path) -> None:
    task_utils = backend_root / "utils" / "task_submission_utils.py"
    if not task_utils.exists():
        return

    text = task_utils.read_text()
    updated = text
    if "import os" not in updated:
        updated = updated.replace("import logging\n", "import logging\nimport os\n", 1)
    updated = updated.replace(
        "r = redis.Redis(host='localhost', port=6379, db=0)",
        "r = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379/0'))",
    )
    if updated != text:
        task_utils.write_text(updated)


def patch_pipeline_adapter(backend_root: Path) -> None:
    pipeline_adapter = backend_root / "services" / "simple_pipeline_adapter.py"
    if not pipeline_adapter.exists():
        return

    text = pipeline_adapter.read_text()
    updated = text

    old = """                else:
                    logger.warning("自动生成字幕失败，创建空大纲")
                    # 创建一个空的大纲文件
                    outlines = []
                    outline_file = metadata_dir / "step1_outline.json"
                    import json
                    with open(outline_file, 'w', encoding='utf-8') as f:
                        json.dump(outlines, f, ensure_ascii=False, indent=2)
"""
    new = """                else:
                    logger.error("自动生成字幕失败，无法继续处理")
                    return {
                        "status": "failed",
                        "project_id": self.project_id,
                        "task_id": self.task_id,
                        "message": "自动生成字幕失败，请上传 SRT 或确认镜像内 Whisper 可用"
                    }
"""
    if old in updated:
        updated = updated.replace(old, new)

    old = """            emit_progress(self.project_id, "SUBTITLE", "字幕处理完成", subpercent=50)
            
            # 阶段3: 内容分析
"""
    new = """            emit_progress(self.project_id, "SUBTITLE", "字幕处理完成", subpercent=50)
            
            if not outlines:
                logger.error("未提取到有效大纲，停止后续处理")
                return {
                    "status": "failed",
                    "project_id": self.project_id,
                    "task_id": self.task_id,
                    "message": "未提取到有效大纲，请检查字幕内容或模型配置"
                }
            
            # 阶段3: 内容分析
"""
    if old in updated:
        updated = updated.replace(old, new)

    if updated != text:
        pipeline_adapter.write_text(updated)


def patch_llm_providers(backend_root: Path) -> None:
    llm_providers = backend_root / "core" / "llm_providers.py"
    if not llm_providers.exists():
        return

    text = llm_providers.read_text()
    updated = text

    old = """    def call(self, prompt: str, input_data: Any = None, **kwargs) -> LLMResponse:
        \"\"\"调用DashScope API\"\"\"
        try:
            full_input = self._build_full_input(prompt, input_data)
            
            response_or_gen = self.generation.call(
                model=self.model_name,
                prompt=full_input,
                api_key=self.api_key,
                stream=False,
                **kwargs
            )
            
            # 处理响应
            # DashScope的GenerationResponse虽然有__iter__方法，但不是真正的迭代器
            # 直接使用响应对象本身
            response = response_or_gen
            
            if response and response.status_code == 200:
                if response.output and response.output.text is not None:
                    return LLMResponse(
                        content=response.output.text,
                        model=self.model_name,
                        finish_reason=getattr(response.output, 'finish_reason', None)
                    )
                else:
                    finish_reason = getattr(response.output, 'finish_reason', 'unknown') if response.output else 'unknown'
                    logger.warning(f\"API请求成功，但输出为空。结束原因: {finish_reason}\")
                    return LLMResponse(content=\"\")
            else:
                code = getattr(response, 'code', 'N/A')
                message = getattr(response, 'message', '未知API错误')
                raise Exception(f\"API调用失败 - Status: {response.status_code}, Code: {code}, Message: {message}\")
                
        except Exception as e:
            logger.error(f\"DashScope调用失败: {str(e)}\")
            raise
    
    def test_connection(self) -> bool:
        \"\"\"测试DashScope连接\"\"\"
        try:
            response = self.call(\"请回复'测试成功'\")
            return \"测试成功\" in response.content or \"success\" in response.content.lower()
        except Exception as e:
            logger.error(f\"DashScope连接测试失败: {e}\")
            return False
"""

    new = """    def call(self, prompt: str, input_data: Any = None, **kwargs) -> LLMResponse:
        \"\"\"调用DashScope API\"\"\"
        try:
            full_input = self._build_full_input(prompt, input_data)

            # 兼容新版 DashScope Chat 接口，同时保留旧版返回结构解析。
            request_kwargs = {
                \"model\": self.model_name,
                \"api_key\": self.api_key,
                \"stream\": False,
                **kwargs,
            }

            if \"messages\" not in request_kwargs and \"prompt\" not in request_kwargs:
                request_kwargs[\"messages\"] = [{\"role\": \"user\", \"content\": full_input}]
                request_kwargs[\"result_format\"] = request_kwargs.get(\"result_format\", \"message\")

            response = self.generation.call(**request_kwargs)

            if not response:
                raise Exception(\"DashScope 未返回响应对象\")

            status_code = getattr(response, \"status_code\", None)
            if status_code != 200:
                code = getattr(response, \"code\", \"N/A\")
                message = getattr(response, \"message\", \"未知API错误\")
                raise Exception(f\"API调用失败 - Status: {status_code}, Code: {code}, Message: {message}\")

            output = getattr(response, \"output\", None)
            content = \"\"
            finish_reason = None

            if output is not None:
                finish_reason = getattr(output, \"finish_reason\", None)
                text_output = getattr(output, \"text\", None)
                if text_output:
                    content = text_output
                else:
                    choices = getattr(output, \"choices\", None) or []
                    if choices:
                        choice = choices[0]
                        if isinstance(choice, dict):
                            finish_reason = choice.get(\"finish_reason\", finish_reason)
                            message = choice.get(\"message\") or {}
                            content = message.get(\"content\", \"\") or choice.get(\"text\", \"\")
                        else:
                            finish_reason = getattr(choice, \"finish_reason\", finish_reason)
                            message = getattr(choice, \"message\", None)
                            if isinstance(message, dict):
                                content = message.get(\"content\", \"\")
                            elif message is not None:
                                content = getattr(message, \"content\", \"\") or \"\"
                            if not content:
                                content = getattr(choice, \"text\", \"\") or \"\"

            if isinstance(content, list):
                content = \"\\n\".join(
                    item.get(\"text\", \"\") if isinstance(item, dict) else str(item)
                    for item in content
                )

            content = (content or \"\").strip()
            if not content:
                logger.warning(\"DashScope 请求成功但未返回文本内容\")

            return LLMResponse(
                content=content,
                model=self.model_name,
                finish_reason=finish_reason
            )

        except Exception as e:
            logger.error(f\"DashScope调用失败: {str(e)}\")
            raise

    def test_connection(self) -> bool:
        \"\"\"测试DashScope连接\"\"\"
        try:
            response = self.call(\"请简短回复：连接成功\")
            return bool((response.content or \"\").strip())
        except Exception as e:
            logger.error(f\"DashScope连接测试失败: {e}\")
            return False
"""

    if old in updated:
        updated = updated.replace(old, new)

    if updated != text:
        llm_providers.write_text(updated)


def main() -> int:
    source_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/autoclip-source")
    patch_frontend(source_root / "frontend" / "src")
    backend_root = source_root / "backend"
    patch_task_utils(backend_root)
    patch_pipeline_adapter(backend_root)
    patch_llm_providers(backend_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
