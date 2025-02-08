import json
import re
from pathlib import Path
from datetime import datetime
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import (
    GroupNormalMessageReceived,
    PersonNormalMessageReceived,
    NormalMessageResponded
)

@register(
    name="GroupMemoryMini",
    description="基于关系管理系统的轻量伪记忆系统",
    version="0.3",
    author="KL"
)
class RelationManager(BasePlugin):
    def __init__(self, host: APIHost):
        self.host = host
        self.data_path = Path("plugins/GroupMemoryMini/data/relation_data.json")
        self.relation_data = {}
        self.pattern = re.compile(r"评价值([+-]?\d+)|评价值\s*[：:]\s*([+-]?\d+)")

    async def initialize(self):
        await self.load_data()

    async def load_data(self):
        try:
            if self.data_path.exists():
                raw_content = self.data_path.read_text(encoding="utf-8")
                if not raw_content.strip():
                    raise json.JSONDecodeError("Empty file", doc="", pos=0)
                self.relation_data = json.loads(raw_content)
                self.ap.logger.info("关系数据加载成功")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            corrupt_path = self.data_path.with_name(f"corrupt_{datetime.now().strftime('%Y%m%d%H%M')}_relation_data.json")
            self.data_path.rename(corrupt_path)
            self.relation_data = {}
            self.ap.logger.error(f"数据文件损坏，已备份至 {corrupt_path}，初始化新数据")
        except Exception as e:
            self.ap.logger.error(f"未知加载错误: {str(e)}")
            self.relation_data = {}

    async def save_data(self):
        try:
            temp_path = self.data_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.relation_data, f, ensure_ascii=False, indent=2)
            temp_path.replace(self.data_path)
        except Exception as e:
            self.ap.logger.error(f"数据保存失败: {str(e)}")

    def get_relation(self, user_id: str) -> dict:
        try:
            data = self.relation_data.get(user_id, {})
            required_keys = {"evaluation", "history", "last_interaction", "custom_note"}
            if not required_keys.issubset(data.keys()):
                raise KeyError("Missing required keys")
            if not isinstance(data["evaluation"], int):
                data["evaluation"] = int(data["evaluation"])
            data["evaluation"] = max(0, min(100, data["evaluation"]))
            if "T" not in data["last_interaction"]:
                data["last_interaction"] = datetime.now().isoformat()
            self.relation_data[user_id] = data
            return data
        except Exception as e:
            self.ap.logger.warning(f"用户 {user_id} 数据损坏，已重置: {str(e)}")
            self.relation_data[user_id] = self._init_user_data()
            return self.relation_data[user_id]

    def _init_user_data(self) -> dict:
        return {
            "evaluation": 50,
            "history": [],
            "last_interaction": datetime.now().isoformat(),
            "custom_note": ""
        }

    @handler(NormalMessageResponded)
    async def handle_ai_response(self, ctx: EventContext):
        event = ctx.event
        user_id = str(event.sender_id)
        
        self.ap.logger.info(f"NormalMessageResponded - Sender ID: {user_id}")
        
        if not hasattr(event, 'response_text') or not event.response_text:
            return

        # 提取评价值调整
        matches = self.pattern.findall(event.response_text)
        total_adjustment = 0
        cleaned_response = event.response_text

        for match in matches:
            value = match[0] or match[1]
            try:
                adjustment = int(value)
                total_adjustment += adjustment
                cleaned_response = cleaned_response.replace(match[0] or match[1], "", 1)
            except ValueError:
                self.ap.logger.warning(f"无效的评价值数值: {value}")

        # 更新评价值
        if total_adjustment != 0:
            relation = self.get_relation(user_id)
            new_evaluation = max(0, min(100, relation["evaluation"] + total_adjustment))
            actual_adjustment = new_evaluation - relation["evaluation"]
            relation["evaluation"] = new_evaluation
            relation["history"].append({
                "timestamp": datetime.now().isoformat(),
                "adjustment": actual_adjustment,
                "reason": "AI自动调整"
            })
            relation["last_interaction"] = datetime.now().isoformat()
            await self.save_data()
            self.ap.logger.info(f"用户 {user_id} 评价值变化: {actual_adjustment}, 当前: {new_evaluation}")

            # 更新回复内容，确保显示最新评价值
            ctx.event.response_text = (
                f"{cleaned_response.strip()}\n"
                f"[系统提示] 评价值已更新，当前为 {new_evaluation}/100。"
            )

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_query(self, ctx: EventContext):
        event = ctx.event
        user_id = str(event.sender_id)

        # 调试日志：确认 sender_id 是否正确
        self.ap.logger.info(f"MessageReceived - Sender ID: {user_id}")
    
        relation = self.get_relation(user_id)

        if event.text_message.strip() == "/查看关系":
            report = (
                f"【关系状态】\n"
                f"• 当前评价值：{relation['evaluation']}/100\n"
                f"• 历史调整：{len(relation['history'])}次\n"
                f"• 最后互动：{relation['last_interaction'][:19]}\n"
                f"• 特别备注：{relation['custom_note'] or '暂无'}"
            )
            if ctx.event.reply is None:
                ctx.event.reply = []
            ctx.event.reply.append(report)
            ctx.prevent_default()
            return

        # 将关系数据注入到 AI 的上下文中
        ctx.add_return("relation_data", {
            "user_id": user_id,
            "evaluation": relation['evaluation'],
            "custom_note": relation['custom_note'] or '无'
        })

        self.ap.logger.info(f"Return values: {ctx.__return_value__}")

    def __del__(self):
        pass
