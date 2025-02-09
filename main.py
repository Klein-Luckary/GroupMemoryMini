import json
import re
from pathlib import Path
from datetime import datetime
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import (
    GroupNormalMessageReceived,
    PersonNormalMessageReceived,
    NormalMessageResponded,
    PromptPreProcessing
)
from pkg.plugin.models import llm_entities

@register(
    name="GroupMemoryMini",
    description="基于关系管理系统的轻量伪记忆系统",
    version="0.5",  # 更新版本号
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
            required_keys = {"evaluation", "history", "last_interaction", "custom_note", "interaction_count"}
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
            "custom_note": "",
            "interaction_count": 0
        }

    @handler(NormalMessageResponded)
    async def handle_ai_response(self, ctx: EventContext):
        event = ctx.event
        user_id = str(event.sender_id)
        
        self.ap.logger.info(f"NormalMessageResponded - Sender ID: {user_id}")
        
        if not hasattr(event, 'response_text') or not event.response_text:
            return

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

            ctx.event.response_text = (
                f"{cleaned_response.strip()}\n"
                f"[系统提示] 评价值已更新，当前为 {new_evaluation}/100。"
            )

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_query(self, ctx: EventContext):
        event = ctx.event
        user_id = str(event.sender_id)

        relation = self.get_relation(user_id)
        relation['interaction_count'] = relation.get('interaction_count', 0) + 1
        relation['last_interaction'] = datetime.now().isoformat()
        await self.save_data()

        if event.text_message.strip() == "/查看关系":
            report = (
                f"【关系状态】\n"
                f"• 当前评价值：{relation['evaluation']}/100\n"
                f"• 历史调整：{len(relation['history'])}次\n"
                f"• 互动次数：{relation['interaction_count']}次\n"
                f"• 最后互动：{relation['last_interaction'][:19]}\n"
                f"• 特别备注：{relation['custom_note'] or '暂无'}"
            )
            if ctx.event.reply is None:
                ctx.event.reply = []
            ctx.event.reply.append(report)
            ctx.prevent_default()
            return

    @handler(PromptPreProcessing)
    async def handle_prompt_preprocessing(self, ctx: EventContext):
        try:
            # 从上下文中获取用户ID
            user_id = None
            if hasattr(ctx.event, 'session') and hasattr(ctx.event.session, 'sender_id'):
                user_id = str(ctx.event.session.sender_id)
            elif hasattr(ctx.event, 'sender_id'):
                user_id = str(ctx.event.sender_id)
            
            if not user_id:
                self.ap.logger.warning("无法获取用户ID，跳过提示预处理")
                return

            relation = self.get_relation(user_id)
            
            system_prompt = (
                f"当前对话用户：{user_id}\n"
                f"综合评分：{relation['evaluation']}/100\n"
                f"特殊标签：{relation['custom_note'] or '无'}\n"
                f"历史互动次数：{relation['interaction_count']}次\n"
                f"最后互动时间：{relation['last_interaction'][:19]}"
            )
            
            ctx.event.default_prompt.insert(
                0,
                llm_entities.Message(role="system", content=system_prompt)
            )
            
            self.ap.logger.debug(f"已插入用户关系提示：{system_prompt}")
        except Exception as e:
            self.ap.logger.error(f"提示预处理失败：{str(e)}")

    def __del__(self):
        pass
