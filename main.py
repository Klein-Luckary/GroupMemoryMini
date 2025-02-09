# plugins/GroupMemoryMini/__init__.py
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
    version="2.0",
    author="KL"
)
class RelationManager(BasePlugin):
    def __init__(self, host: APIHost):
        super().__init__(host)
        self.data_path = Path("plugins/GroupMemoryMini/data/relation_data.json")
        self.relation_data = {}
        self.pattern = re.compile(r"评价值([+-]?\d+)|评价值\s*[：:]\s*([+-]?\d+)")

    async def initialize(self):
        """插件初始化时加载数据"""
        await self.load_data()

    async def load_data(self):
        """加载用户关系数据"""
        try:
            if self.data_path.exists():
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    self.relation_data = json.load(f)
        except Exception as e:
            self.ap.logger.error(f"加载数据失败: {str(e)}")
            self.relation_data = {}

    async def save_data(self):
        """保存用户关系数据"""
        try:
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump(self.relation_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.ap.logger.error(f"保存数据失败: {str(e)}")

    def get_relation(self, user_id: str) -> dict:
        """获取或初始化用户关系数据"""
        return self.relation_data.setdefault(user_id, {
            "evaluation": 50,
            "history": [],
            "last_interaction": datetime.now().isoformat(),
            "custom_note": "",
            "interaction_count": 0
        })

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_message(self, ctx: EventContext):
        """处理用户消息"""
        user_id = str(ctx.event.sender_id)
        relation = self.get_relation(user_id)
        
        # 更新互动数据
        relation["interaction_count"] += 1
        relation["last_interaction"] = datetime.now().isoformat()
        await self.save_data()

        if ctx.event.text_message.strip() == "/查看关系":
            report = (
                f"【关系状态】\n"
                f"• 当前评分：{relation['evaluation']}/100\n"
                f"• 互动次数：{relation['interaction_count']}次\n"
                f"• 最后互动：{relation['last_interaction'][:19]}\n"
                f"• 特别备注：{relation['custom_note'] or '暂无'}"
            )
            ctx.event.reply = [report]
            ctx.prevent_default()

        # 在消息处理时动态修改默认提示
        if hasattr(ctx.event, 'alter'):
            relation_prompt = (
                f"[用户关系档案]\n"
                f"用户ID: {user_id}\n"
                f"综合评分: {relation['evaluation']}/100\n"
                f"特殊标签: {relation['custom_note'] or '无'}\n"
                f"历史互动: {relation['interaction_count']}次\n"
                f"最后活跃: {relation['last_interaction'][:19]}"
            )
            ctx.event.alter = f"{relation_prompt}\n\n{ctx.event.alter or ctx.event.text_message}"

    @handler(NormalMessageResponded)
    async def handle_response(self, ctx: EventContext):
        """处理AI回复"""
        event = ctx.event
        user_id = str(event.sender_id)
        
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

            # 更新回复内容
            ctx.event.response_text = (
                f"{cleaned_response.strip()}\n"
                f"[系统提示] 评价值已更新，当前为 {new_evaluation}/100。"
            )
            
    def __del__(self):
        pass
