import json
import re
from pathlib import Path
from datetime import datetime
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import GroupNormalMessageReceived, PersonNormalMessageReceived

@register(
    name="GroupMemoryMini",
    description="智能关系管理系统",
    version="2.0",
    author="KL"
)
class RelationManager(BasePlugin):
    def __init__(self, host: APIHost):
        self.host = host
        self.data_path = Path("data/relation_data.json")
        self.relation_data = {}
        self.reply_pattern = re.compile(r"好感度([+-]\d+)")  # 匹配AI回复中的好感度调整标记

    async def initialize(self):
        """加载关系数据"""
        await self.load_data()

    async def load_data(self):
        """异步加载数据"""
        try:
            if self.data_path.exists():
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self.relation_data = json.load(f)
                self.ap.logger.info("关系数据加载成功")
        except Exception as e:
            self.ap.logger.error(f"数据加载失败: {str(e)}")
            self.relation_data = {}

    async def save_data(self):
        """保存数据（带版本控制）"""
        try:
            backup_path = self.data_path.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d%H%M')}")
            if self.data_path.exists():
                self.data_path.rename(backup_path)

            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.relation_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.ap.logger.error(f"数据保存失败: {str(e)}")

    def get_relation(self, user_id: str) -> dict:
        """获取或初始化用户关系数据"""
        if user_id not in self.relation_data:
            self.relation_data[user_id] = {
                "score": 50,  # 初始分数
                "history": [],
                "last_interaction": datetime.now().isoformat(),
                "custom_note": ""
            }
        return self.relation_data[user_id]

    def update_score(self, user_id: str, delta: int, reason: str):
        """更新关系分数并记录历史"""
        relation = self.get_relation(user_id)
        new_score = max(0, min(100, relation["score"] + delta))
        actual_delta = new_score - relation["score"]

        relation["score"] = new_score
        relation["history"].append({
            "timestamp": datetime.now().isoformat(),
            "delta": actual_delta,
            "reason": reason
        })
        relation["last_interaction"] = datetime.now().isoformat()

        # 保留最近50条记录
        relation["history"] = relation["history"][-50:]

    async def generate_context_prompt(self, user_id: str) -> str:
        """生成上下文提示"""
        relation = self.get_relation(user_id)
        last_5 = [f"{h['delta']:+} ({h['reason']})" for h in relation["history"][-5:]

        return f"""
        [关系上下文] 
        当前用户：{user_id}
        关系分数：{relation['score']}/100 
        近期变动：{", ".join(last_5) if last_5 else "无"}
        特别备注：{relation['custom_note'] or "无"}
        """

    @handler(PersonNormalMessageReceived)
    async def person_normal_message_received(self, ctx: EventContext):
        """处理接收个人消息"""
        user_id = str(ctx.event.sender_id)
        context_prompt = await self.generate_context_prompt(user_id)
        
        # 在原始消息前添加关系上下文
        original_msg = ctx.event.text_message
        ctx.event.text_message = f"{context_prompt}\n用户消息：{original_msg}"

        # 更新最后互动时间
        self.get_relation(user_id)  # 确保数据存在
        await self.save_data()

    @handler(GroupNormalMessageReceived)
    async def group_normal_message_received(self, ctx: EventContext):
        """处理接收群消息"""
        user_id = str(ctx.event.sender_id)
        context_prompt = await self.generate_context_prompt(user_id)

        # 在原始消息前添加关系上下文
        original_msg = ctx.event.text_message
        ctx.event.text_message = f"{context_prompt}\n用户消息：{original_msg}"

        # 更新最后互动时间
        self.get_relation(user_id)  # 确保数据存在
        await self.save_data()

    def __del__(self):
        """插件卸载时保存数据"""
        import asyncio
        asyncio.run(self.save_data())
