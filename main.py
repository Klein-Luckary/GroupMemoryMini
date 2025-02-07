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
    description="智能关系管理系统",
    version="2.1",
    author="KL"
)
class RelationManager(BasePlugin):
    def __init__(self, host: APIHost):
        self.host = host
        self.data_path = Path("plugins/GroupMemoryMini/data/relation_data.json")
        self.relation_data = {}
        # 增强正则匹配模式，支持中文符号和空格
        self.reply_pattern = re.compile(r"好感度\s*[：:]\s*([+-]\d+)")

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
        """安全保存数据（带原子操作）"""
        try:
            # 先保存到临时文件
            temp_path = self.data_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.relation_data, f, ensure_ascii=False, indent=2)
            
            # 替换原文件
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
    async def handle_response(self, ctx: EventContext):
        """处理AI的回复消息"""
        response = ctx.event.response
        sender_id = str(ctx.event.receiver_id)  # 接收者即消息发送者
        
        # 匹配好感度调整
        match = self.reply_pattern.search(response)
        if match:
            try:
                adjustment = int(match.group(1))
                # 获取用户数据
                relation = self.get_relation(sender_id)
                
                # 应用分数调整（限制在0-100之间）
                new_score = max(0, min(100, relation["score"] + adjustment))
                actual_adjustment = new_score - relation["score"]
                
                if actual_adjustment != 0:
                    relation["score"] = new_score
                    relation["history"].append({
                        "timestamp": datetime.now().isoformat(),
                        "adjustment": actual_adjustment,
                        "reason": "AI回复触发"
                    })
                    relation["last_interaction"] = datetime.now().isoformat()
                    
                    await self.save_data()
                    self.ap.logger.info(f"用户 {sender_id} 好感度变化: {actual_adjustment}, 当前: {new_score}")
                
                # 从回复内容移除调整标记
                new_response = self.reply_pattern.sub("", response).strip()
                ctx.event.response = new_response if new_response else "[好感度已更新]"

            except ValueError:
                self.ap.logger.warning(f"无效的好感度数值: {match.group(1)}")

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_query(self, ctx: EventContext):
        """统一处理查询命令"""
        msg = ctx.event.text_message
        user_id = str(ctx.event.sender_id)
        
        if msg.strip() == "/查看好感度":
            relation = self.get_relation(user_id)
            
            # 生成关系报告
            report = (
                f"【关系状态】\n"
                f"当前好感：{relation['score']}/100\n"
                f"历史调整：{len(relation['history'])}次\n"
                f"最后互动：{relation['last_interaction'][:10]}\n"
                f"特别备注：{relation['custom_note'] or '暂无备注'}"
            )
            
            ctx.add_return("reply", [report])
            ctx.prevent_default()

    def __del__(self):
        pass
