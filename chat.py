#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
A-Stock Trading CLI 对话入口
基于 LLM Function Calling 的命令行交互式股票分析系统
"""

import json
import os
import sys
import time
import threading
import requests
from datetime import datetime

from models import SessionLocal
from db import get_all_configs, get_config
from cli_tools import TOOLS, execute_tool
from init_agents import init_default_agents

# ==================== 颜色输出 ====================

class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BG_BLUE = '\033[44m'

    @staticmethod
    def disable():
        """在不支持ANSI的终端上禁用颜色"""
        Colors.RESET = ''
        Colors.BOLD = ''
        Colors.DIM = ''
        Colors.RED = ''
        Colors.GREEN = ''
        Colors.YELLOW = ''
        Colors.BLUE = ''
        Colors.MAGENTA = ''
        Colors.CYAN = ''
        Colors.WHITE = ''
        Colors.BG_BLUE = ''


# 检测是否支持颜色
if os.name == 'nt':
    try:
        os.system('')  # 启用Windows ANSI支持
    except Exception:
        Colors.disable()


# ==================== 对话管理器 ====================

class ChatManager:
    """管理与LLM的多轮对话"""

    SYSTEM_PROMPT = """你是 A-Stock Trading 智能助手，一个专业的A股交易分析系统。你可以通过调用工具来获取实时股票数据、技术指标、资金流向、基本面信息，并能启动多Agent辩论分析、管理自选股、筛选策略等。

你的核心能力：
1. **股票查询与分析**：获取实时行情、K线数据、技术指标、资金流向、基本面数据
2. **K线图表**：绘制各种周期的K线图并自动打开查看
3. **多Agent辩论**：启动多个AI分析师从不同角度分析股票，进行辩论并生成综合报告（后台异步执行）
4. **自选股管理**：添加、删除、查看自选股
5. **策略筛选**：筛选强势股、低位启动股
6. **Agent管理**：创建、修改、删除分析Agent
7. **系统配置**：查看和设置AI供应商、API Key等配置

使用规则：
- 当用户提到股票名称时，请先通过工具获取对应的股票代码
- 分析股票时，根据用户需求选择性地调用工具，不要一次获取所有数据
- 辩论任务是异步的，启动后会在后台运行，可以随时查看进度
- 回答时使用中文，保持专业但易懂的风格
- 对于投资建议，始终提醒用户注意风险

当辩论任务完成时，系统会自动通知你。"""

    def __init__(self):
        self.messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT}
        ]
        self.provider = None
        self.model = None
        self.api_key = None
        self.base_url = None
        self.pending_notifications = []  # 异步通知队列
        self._lock = threading.Lock()

    def load_config(self):
        """从数据库加载AI配置"""
        db = SessionLocal()
        try:
            configs = get_all_configs(db)
            self.provider = configs.get('default_ai_provider', 'deepseek')

            provider_urls = {
                'openai': 'https://api.openai.com/v1',
                'deepseek': 'https://api.deepseek.com/v1',
                'qwen': os.getenv('DASHSCOPE_API_BASE', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
                'siliconflow': os.getenv('SILICONFLOW_API_BASE', 'https://api.siliconflow.cn') + '/v1',
                'grok': 'https://api.x.ai/v1',
            }
            default_models = {
                'openai': 'gpt-4o',
                'deepseek': 'deepseek-chat',
                'qwen': 'qwen-plus',
                'siliconflow': 'Qwen/Qwen2.5-72B-Instruct',
                'grok': 'grok-4-0709',
            }

            self.api_key = configs.get(f'{self.provider}_api_key', '')
            self.base_url = provider_urls.get(self.provider, 'https://api.openai.com/v1')
            self.model = configs.get('default_model') or default_models.get(self.provider, 'gpt-4o')

            return bool(self.api_key)
        finally:
            db.close()

    def debate_callback(self, job_id, code, status):
        """辩论任务完成回调"""
        with self._lock:
            if status == "completed":
                self.pending_notifications.append(
                    f"\n📊 辩论任务完成！任务ID: {job_id}，股票: {code}\n"
                    f"   输入「查看报告 {job_id}」或让我获取报告内容。"
                )
            elif status == "failed":
                self.pending_notifications.append(
                    f"\n❌ 辩论任务失败！任务ID: {job_id}，股票: {code}\n"
                    f"   输入「查看任务状态 {job_id}」了解详情。"
                )

    def get_notifications(self):
        """获取并清空待处理通知"""
        with self._lock:
            notifications = self.pending_notifications.copy()
            self.pending_notifications.clear()
            return notifications

    def chat(self, user_input: str) -> str:
        """
        发送用户消息并获取AI回复（含Function Calling循环）
        """
        if not self.api_key:
            return "⚠️ 未配置AI API Key。请使用命令 /config 进行配置。"

        # 添加用户消息
        self.messages.append({"role": "user", "content": user_input})

        # Gemini不支持标准Function Calling，走特殊处理
        if self.provider == 'gemini':
            return self._chat_gemini(user_input)

        # OpenAI兼容接口的Function Calling循环
        max_iterations = 10
        for iteration in range(max_iterations):
            try:
                response = self._call_llm()
            except Exception as e:
                error_msg = f"AI调用失败: {str(e)}"
                self.messages.append({"role": "assistant", "content": error_msg})
                return error_msg

            message = response.get("choices", [{}])[0].get("message", {})

            # 检查是否有工具调用
            tool_calls = message.get("tool_calls")

            if tool_calls:
                # 添加assistant消息（含tool_calls）
                self.messages.append(message)

                # 执行每个工具调用
                for tc in tool_calls:
                    func_name = tc["function"]["name"]
                    try:
                        func_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        func_args = {}

                    print(f"  {Colors.DIM}🔧 调用工具: {func_name}({json.dumps(func_args, ensure_ascii=False)[:80]}){Colors.RESET}")

                    result = execute_tool(func_name, func_args, debate_callback=self.debate_callback)

                    # 添加工具结果
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result
                    })
            else:
                # 没有工具调用，返回最终回复
                content = message.get("content", "")
                self.messages.append({"role": "assistant", "content": content})
                return content

        return "⚠️ 工具调用次数过多，请简化您的问题。"

    def _call_llm(self):
        """调用LLM API（OpenAI兼容格式）"""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 构建请求体
        body = {
            "model": self.model,
            "messages": self.messages,
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0.7,
        }

        response = requests.post(url, headers=headers, json=body, timeout=120)
        response.raise_for_status()
        return response.json()

    def _chat_gemini(self, user_input):
        """Gemini特殊处理（不支持标准OpenAI Function Calling格式）"""
        # 对Gemini使用简单的prompt方式，列出可用工具让它选择
        tool_descriptions = "\n".join([
            f"- {t['function']['name']}: {t['function']['description']}"
            for t in TOOLS
        ])
        prompt = f"""你有以下工具可以使用：
{tool_descriptions}

如果需要调用工具，请严格按以下JSON格式回复（不要加任何其他内容）：
{{"tool": "工具名", "args": {{参数}}}}

如果不需要调用工具，直接用自然语言回复。

用户问题：{user_input}"""

        try:
            from ai_service import AIService
            result = AIService.call_gemini(self.api_key, self.model, prompt)

            # 尝试解析工具调用
            try:
                parsed = json.loads(result.strip())
                if "tool" in parsed:
                    tool_name = parsed["tool"]
                    tool_args = parsed.get("args", {})
                    print(f"  {Colors.DIM}🔧 调用工具: {tool_name}{Colors.RESET}")
                    tool_result = execute_tool(tool_name, tool_args, debate_callback=self.debate_callback)

                    # 让Gemini基于工具结果生成回复
                    summary_prompt = f"工具 {tool_name} 的执行结果：\n{tool_result}\n\n请基于以上结果，用中文回答用户的问题：{user_input}"
                    final = AIService.call_gemini(self.api_key, self.model, summary_prompt)
                    self.messages.append({"role": "assistant", "content": final})
                    return final
            except (json.JSONDecodeError, KeyError):
                pass

            self.messages.append({"role": "assistant", "content": result})
            return result
        except Exception as e:
            error_msg = f"Gemini调用失败: {str(e)}"
            self.messages.append({"role": "assistant", "content": error_msg})
            return error_msg

    def trim_history(self, max_messages=40):
        """裁剪对话历史，保留system prompt和最近的消息"""
        if len(self.messages) > max_messages:
            # 保留system prompt + 最近的消息
            self.messages = [self.messages[0]] + self.messages[-(max_messages - 1):]


# ==================== 内置命令 ====================

def handle_builtin_command(cmd: str, chat_mgr: ChatManager) -> str | None:
    """
    处理内置命令（以/开头），返回响应文本。
    如果不是内置命令，返回None。
    """
    cmd = cmd.strip()
    if not cmd.startswith('/'):
        return None

    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command in ('/help', '/h', '/?'):
        return f"""
{Colors.BOLD}📖 A-Stock Trading CLI 帮助{Colors.RESET}

{Colors.CYAN}内置命令：{Colors.RESET}
  /help, /h       显示此帮助信息
  /config          查看当前AI配置
  /config set <key> <value>  设置配置（如 /config set deepseek_api_key sk-xxx）
  /agents          查看Agent列表
  /clear           清除对话历史
  /history         查看对话历史摘要
  /quit, /exit     退出程序

{Colors.CYAN}对话示例：{Colors.RESET}
  查一下贵州茅台的实时行情
  分析600519的技术指标
  画一下茅台的日K线
  帮我深度分析一下000001
  加自选 600519
  看看自选股
  帮我找找今天的强势股
  创建一个专注短线分析的Agent
  查看辩论任务进度
"""

    elif command == '/config':
        if arg.startswith('set '):
            kv = arg[4:].strip().split(maxsplit=1)
            if len(kv) == 2:
                result = execute_tool("config_set", {"key": kv[0], "value": kv[1]})
                # 重新加载配置
                chat_mgr.load_config()
                return f"✅ {json.loads(result).get('message', '配置已更新')}\n配置已重新加载。"
            return "用法: /config set <key> <value>"
        else:
            result = execute_tool("config_get", {})
            data = json.loads(result)
            configs = data.get("configs", {})
            lines = [f"\n{Colors.BOLD}⚙️ 当前配置：{Colors.RESET}"]
            lines.append(f"  AI供应商: {Colors.GREEN}{chat_mgr.provider}{Colors.RESET}")
            lines.append(f"  模型: {Colors.GREEN}{chat_mgr.model}{Colors.RESET}")
            for k, v in configs.items():
                lines.append(f"  {k}: {v}")
            return "\n".join(lines)

    elif command == '/agents':
        result = execute_tool("agent_list", {"enabled_only": False})
        data = json.loads(result)
        agents = data.get("agents", [])
        lines = [f"\n{Colors.BOLD}🤖 Agent列表 (共{len(agents)}个)：{Colors.RESET}"]
        for a in agents:
            status = f"{Colors.GREEN}✓{Colors.RESET}" if a['enabled'] else f"{Colors.RED}✗{Colors.RESET}"
            lines.append(f"  {status} [{a['id']}] {a['name']} ({a['type']}) - {a['ai_provider']}/{a['model']}")
        return "\n".join(lines)

    elif command == '/clear':
        chat_mgr.messages = [chat_mgr.messages[0]]
        return "🗑️ 对话历史已清除。"

    elif command == '/history':
        count = len(chat_mgr.messages) - 1  # 排除system
        user_msgs = sum(1 for m in chat_mgr.messages if m.get('role') == 'user')
        assistant_msgs = sum(1 for m in chat_mgr.messages if m.get('role') == 'assistant')
        tool_msgs = sum(1 for m in chat_mgr.messages if m.get('role') == 'tool')
        return (f"📜 对话历史：共 {count} 条消息\n"
                f"   用户: {user_msgs} | 助手: {assistant_msgs} | 工具调用: {tool_msgs}")

    elif command in ('/quit', '/exit', '/q'):
        print(f"\n{Colors.YELLOW}👋 再见！祝投资顺利！{Colors.RESET}\n")
        sys.exit(0)

    else:
        return f"未知命令: {command}，输入 /help 查看帮助。"


# ==================== 主入口 ====================

def print_banner():
    """打印启动横幅"""
    banner = f"""
{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════╗
║         A-Stock Trading CLI 智能分析系统             ║
║         基于多Agent辩论的股票分析助手                ║
╚══════════════════════════════════════════════════════╝{Colors.RESET}

{Colors.DIM}输入自然语言与AI助手对话，输入 /help 查看帮助，输入 /quit 退出{Colors.RESET}
"""
    print(banner)


def main():
    """主函数"""
    print_banner()

    # 初始化默认Agent
    print(f"{Colors.DIM}正在初始化系统...{Colors.RESET}")
    try:
        init_default_agents()
    except Exception as e:
        print(f"{Colors.YELLOW}⚠️ Agent初始化警告: {e}{Colors.RESET}")

    # 创建对话管理器
    chat_mgr = ChatManager()

    # 加载配置
    if not chat_mgr.load_config():
        print(f"""
{Colors.YELLOW}⚠️ 未检测到AI API Key配置。{Colors.RESET}
请先配置API Key，例如：
  {Colors.GREEN}/config set deepseek_api_key sk-your-key-here{Colors.RESET}
  {Colors.GREEN}/config set default_ai_provider deepseek{Colors.RESET}
""")
    else:
        print(f"{Colors.GREEN}✅ 已加载配置：{chat_mgr.provider}/{chat_mgr.model}{Colors.RESET}\n")

    # 主对话循环
    while True:
        try:
            # 检查异步通知
            notifications = chat_mgr.get_notifications()
            for note in notifications:
                print(f"{Colors.MAGENTA}{note}{Colors.RESET}")

            # 获取用户输入
            user_input = input(f"{Colors.BOLD}{Colors.BLUE}You > {Colors.RESET}").strip()

            if not user_input:
                continue

            # 检查内置命令
            builtin_result = handle_builtin_command(user_input, chat_mgr)
            if builtin_result is not None:
                print(builtin_result)
                continue

            # AI对话
            print(f"{Colors.DIM}思考中...{Colors.RESET}")
            start_time = time.time()

            response = chat_mgr.chat(user_input)

            elapsed = time.time() - start_time
            print(f"\n{Colors.BOLD}{Colors.GREEN}AI > {Colors.RESET}{response}")
            print(f"{Colors.DIM}({elapsed:.1f}s){Colors.RESET}\n")

            # 定期裁剪历史
            chat_mgr.trim_history()

        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}(按 Ctrl+C 中断，输入 /quit 退出){Colors.RESET}")
            continue
        except EOFError:
            print(f"\n{Colors.YELLOW}👋 再见！{Colors.RESET}")
            break
        except Exception as e:
            print(f"{Colors.RED}❌ 错误: {e}{Colors.RESET}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    main()
