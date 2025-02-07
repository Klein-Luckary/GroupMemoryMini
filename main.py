iimport json
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
    description="智能关系管理系统",
    version="3.1",
    author="KL"
)
class RelationManager(BasePlugin):
    def __init__(self, host: APIHost):
        self.host = host
        self.data_path = Path("plugins/GroupMemoryMini/data/relation_data.json")
        self.relation_data = {}
        # 匹配AI回复中的好感度调整标记（支持多种格式）
        self.pattern = re.compile(r"\[好感度([+-]?\d+)\]|好感度\s*[：:]\s*([+-]?\d+)")

    async def initialize(self):
        """异步初始化"""
        await self.load_data()

    async def load_data(self):
        """加载关系数据"""
        try:
            if self.data_path.exists():
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self.relation_data = json.load(f)
                self.ap.logger.info("关系数据加载成功")
        except Exception as e:
            self.ap.logger.error(f"数据加载失败: {str(e)}")
            self.relation_data = {}

    async def save_data(self):
        """原子化保存数据"""
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
                "score": 50,
                "history": [],
                "last_interaction": datetime.now().isoformat(),
                "custom_note": ""
            }
        return self.relation_data[user_id]

    @handler(NormalMessageResponded)
    async def handle_ai_response(self, ctx: EventContext):
        """处理AI的回复消息"""
        # 获取事件对象属性
        event = ctx.event
        
        # 获取接收者ID（根据事件模型，sender_id是消息发送者）
        user_id = str(event.sender_id)
        
        # 解析回复内容
        if response_text := event.response_text:
            # 匹配所有调整指令
            matches = self.pattern.findall(response_text)
            
            total_adjustment = 0
            cleaned_response = response_text
            
            for match in matches:
                # 合并两个捕获组的匹配结果
                value = match[0] or match[1]
                
                try:
                    adjustment = int(value)
                    total_adjustment += adjustment
                    # 从回复内容中移除标记
                    cleaned_response = cleaned_response.replace(match[0] or match[1], "", 1)
                except ValueError:
                    self.ap.logger.warning(f"无效的好感度数值: {value}")

            if total_adjustment != 0:
                # 更新用户数据
                relation = self.get_relation(user_id)
                new_score = max(0, min(100, relation["score"] + total_adjustment))
                actual_adjustment = new_score - relation["score"]
                
                relation["score"] = new_score
                relation["history"].append({
                    "timestamp": datetime.now().isoformat(),
                    "adjustment": actual_adjustment,
                    "reason": "AI自动调整"
                })
                relation["last_interaction"] = datetime.now().isoformat()
                
                await self.save_data()
                self.ap.logger.info(f"用户 {user_id} 好感度变化: {actual_adjustment}, 当前: {new_score}")

                # 更新回复内容
                ctx.event.response_text = cleaned_response.strip() or "[好感度已更新]"

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_query(self, ctx: EventContext):
        """处理查询请求"""
        event = ctx.event
        
        if event.text_message.strip() == "/查看好感度":
            user_id = str(event.sender_id)
            relation = self.get_relation(user_id)
            
            report = (
                f"【关系状态】\n"
                f"• 当前好感：{relation['score']}/100\n"
                f"• 历史调整：{len(relation['history'])}次\n"
                f"• 最后互动：{relation['last_interaction'][:19]}\n"
                f"• 特别备注：{relation['custom_note'] or '暂无'}"
            )
            
            # 设置回复内容
            if ctx.event.reply is None:
                ctx.event.reply = []
            ctx.event.reply.append(report)
            ctx.prevent_default()

    def __del__(self):
        pass
