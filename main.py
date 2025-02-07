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
            if backup_path.exists():
                backup_path.unlink()  # 删除旧的备份文件

            if self.data_path.exists():
                self.data_path.rename(backup_path)

            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.relation_data, f, ensure_ascii=False, indent=2)
            self.ap.logger.info("数据保存成功")  # 添加日志
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

        self.ap.logger.info(f"用户 {user_id} 好感度变化：{actual_delta}，当前：{relation['score']}")  # 添加日志

    @handler(PersonNormalMessageReceived)
    async def handle_person_message(self, ctx: EventContext):
        """处理接收个人消息"""
        user_id = str(ctx.event.sender_id)
        message = ctx.event.text_message

        # 更新最后互动时间
        self.get_relation(user_id)  # 确保用户数据存在

        if message == "/查看好感度":
            await self.handle_query_command(ctx, user_id)
        else:
            # 在这里可以根据消息内容更新好感度
            self.update_score(user_id, 1, "用户发送消息")  # 示例：增加1分
            await self.save_data()  # 保存数据

    @handler(GroupNormalMessageReceived)
    async def handle_group_message(self, ctx: EventContext):
        """处理接收群消息"""
        user_id = str(ctx.event.sender_id)
        message = ctx.event.text_message

        # 更新最后互动时间
        self.get_relation(user_id)  # 确保用户数据存在

        if message == "/查看好感度":
            await self.handle_query_command(ctx, user_id)
        else:
            # 在这里可以根据消息内容更新好感度
            self.update_score(user_id, 1, "用户发送群消息")  # 示例：增加1分
            await self.save_data()  # 保存数据

    async def handle_query_command(self, ctx: EventContext, user_id: str):
        """处理查询好感度的命令"""
        relation = self.get_relation(user_id)

        response = (
            f"【关系状态】\n"
            f"当前分数：{relation['score']}/100\n"
            f"最后互动：{relation['last_interaction'][:10]}\n"
            f"特别备注：{relation['custom_note'] or '无'}"
        )

        ctx.add_return("reply", [response])
        ctx.prevent_default()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """插件卸载时保存数据"""
        await self.save_data()
