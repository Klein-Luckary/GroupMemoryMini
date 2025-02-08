import json
import re
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import (
    GroupNormalMessageReceived,
    PersonNormalMessageReceived,
    NormalMessageResponded
)

@register(
    name="GroupMemoryMini",
    description="基于用户关系管理的伪记忆系统",
    version="0.7",
    author="KL"
)
class RelationManager(BasePlugin):
    def __init__(self, host: APIHost):
        self.host = host
        self.data_path = Path("plugins/GroupMemoryMini/data/relation_data.json")
        self.relation_data = {}
        # 匹配AI回复中的评价值调整标记
        self.pattern = re.compile(r"\[评价值([+-]?\d+)\]|评价值\s*[：:]\s*([+-]?\d+)")
        
        # 上下文提示模板
        self.context_template = (
            "[系统记忆] 对话对象：{username} | "
            "当前评价：{evaluation}/1000 | "
            "历史互动：{history_count}次 | "
            "备注：{note}\n\n"
            "{original_message}"
        )

    async def initialize(self):
        """异步初始化"""
        await self.load_data()

    async def load_data(self):
        """安全加载数据"""
        try:
            if self.data_path.exists():
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self.relation_data = json.load(f)
                self.ap.logger.info("关系数据加载成功")
        except Exception as e:
            self.ap.logger.error(f"数据加载失败: {str(e)}")
            self.relation_data = {}

    async def save_data(self):
        """原子化保存"""
        try:
            temp_path = self.data_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.relation_data, f, ensure_ascii=False, indent=2)
            temp_path.replace(self.data_path)
        except Exception as e:
            self.ap.logger.error(f"数据保存失败: {str(e)}")

    def get_relation(self, user_id: str) -> dict:
        """获取或初始化用户关系数据"""
        if user_id not in self.relation_data:
            self.relation_data[user_id] = {
                "evaluation": 300,  # 初始评价值
                "history": [],
                "last_interaction": datetime.now().isoformat(),
                "custom_note": "",
                "username": f"用户{user_id}"  # 初始用户名
            }
        return self.relation_data[user_id]

    @handler(GroupNormalMessageReceived, PersonNormalMessageReceived)
    async def add_context_prompt(self, ctx: EventContext):
        """添加对话上下文提示"""
        event = ctx.event
        user_id = str(event.sender_id)
        
        # 获取关系数据
        relation = self.get_relation(user_id)
        
        # 构造上下文提示
        context_prompt = self.context_template.format(
            username=relation["username"],
            evaluation=relation["evaluation"],
            history_count=len(relation["history"]),
            note=relation["custom_note"] or "暂无备注",
            original_message=event.text_message
        )
        
        # 修改原始消息（添加前置提示）
        event.text_message = context_prompt

    @handler(NormalMessageResponded)
    async def handle_ai_response(self, ctx: EventContext):
        """处理AI回复"""
        event = ctx.event
        user_id = str(event.sender_id)
        
        if response_text := event.response_text:
            # 匹配评价值调整指令
            matches = self.pattern.findall(response_text)
            total_adjustment = 0
            cleaned_response = response_text
            
            for match in matches:
                value = match[0] or match[1]
                try:
                    adjustment = int(value)
                    total_adjustment += adjustment
                    cleaned_response = cleaned_response.replace(match[0] or match[1], "", 1)
                except ValueError:
                    self.ap.logger.warning(f"无效的评价值: {value}")

            if total_adjustment != 0:
                relation = self.get_relation(user_id)
                new_eval = max(0, min(1000, relation["evaluation"] + total_adjustment))
                actual_adj = new_eval - relation["evaluation"]
                
                relation["evaluation"] = new_eval
                relation["history"].append({
                    "timestamp": datetime.now().isoformat(),
                    "adjustment": actual_adj,
                    "reason": "AI自动调整"
                })
                relation["last_interaction"] = datetime.now().isoformat()
                
                await self.save_data()
                self.ap.logger.info(f"用户 {user_id} 评价变更: {actual_adj}")

                # 更新回复内容
                ctx.event.response_text = cleaned_response.strip() or "[评价值已更新]"

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_query(self, ctx: EventContext):
        """处理查询命令"""
        event = ctx.event
        if event.text_message.strip() == "/查询评价":
            user_id = str(event.sender_id)
            relation = self.get_relation(user_id)
            
            report = (
                f"【用户评价】\n"
                f"• 用户：{relation['username']}\n"
                f"• 当前评价：{relation['evaluation']}/1000\n"
                f"• 最后互动：{relation['last_interaction'][:19]}\n"
                f"• 特别备注：{relation['custom_note'] or '无'}"
            )
            
            ctx.add_return("reply", [report])
            ctx.prevent_default()

    def __del__(self):
        pass
