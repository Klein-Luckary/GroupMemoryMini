import json
import re
from pathlib import Path
from datetime import datetime
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import GroupNormalMessageReceived, PersonNormalMessageReceived, LlmResponseGenerated

@register(
    name="GroupMemoryMini",
    description="伪关系管理系统",
    version="0.1",
    author="KL"
)
class RelationManager(BasePlugin):
    def __init__(self, host: APIHost):
        self.host = host
        self.data_path = Path("data/relation_data.json")
        self.relation_data = {}
        self.reply_pattern = re.compile(r"\(好感度([+-]\d+)\)")  # 匹配AI回复中的好感度调整标记

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

    async def generate_context_prompt(self, user_id: str, context_type: str = "group") -> str:
        """生成上下文提示"""
        relation = self.get_relation(user_id)
        last_5 = [f"{h['delta']:+} ({h['reason']})" for h in relation["history"][-5:]]
        
        return f"""
        [关系上下文] 
        当前用户：{user_id}
        关系分数：{relation['score']}/100 
        近期变动：{", ".join(last_5) if last_5 else "无"}
        特别备注：{relation['custom_note'] or "无"}
        """

    @handler(GroupNormalMessageReceived, PersonNormalMessageReceived)
    async def handle_message(self, ctx: EventContext):
        """处理接收消息"""
        try:
            user_id = str(ctx.event.sender_id)
            group_id = str(ctx.event.group_id) if hasattr(ctx.event, 'group_id') else "private"
            
            # 生成关系提示
            context_prompt = await self.generate_context_prompt(user_id)
            
            # 在原始消息前添加关系上下文
            original_msg = ctx.event.text_message
            ctx.event.text_message = f"{context_prompt}\n用户消息：{original_msg}"
            
            # 更新最后互动时间
            self.get_relation(user_id)  # 确保数据存在
            await self.save_data()

        except Exception as e:
            self.ap.logger.error(f"消息处理出错: {str(e)}")

    @handler(LlmResponseGenerated)
    async def handle_ai_response(self, ctx: EventContext):
        """处理AI生成的回复"""
        try:
            user_id = str(ctx.event.receiver_id)
            ai_response = ctx.event.response
            
            # 检测好感度调整标记
            match = self.reply_pattern.search(ai_response)
            if match:
                delta = int(match.group(1))
                reason = "AI自动评估"
                
                # 清理回复中的标记
                clean_response = self.reply_pattern.sub("", ai_response).strip()
                ctx.event.response = clean_response
                
                # 更新分数
                self.update_score(user_id, delta, reason)
                await self.save_data()
                
                self.ap.logger.info(f"用户 {user_id} 好感度变化：{delta}，当前：{self.get_relation(user_id)['score']}")

            # 根据分数调整语气
            relation = self.get_relation(user_id)
            if relation["score"] >= 80:
                ctx.event.response = f"（热情）{ctx.event.response}"
            elif relation["score"] <= 30:
                ctx.event.response = f"（冷淡）{ctx.event.response}"

        except Exception as e:
            self.ap.logger.error(f"回复处理出错: {str(e)}")

    @handler(command="/查看好感度")
    async def handle_query_command(self, ctx: EventContext):
        """处理查询命令"""
        user_id = str(ctx.event.sender_id)
        relation = self.get_relation(user_id)
        
        response = (
            f"【关系状态】\n"
            f"当前分数：{relation['score']}/100\n"
            f"最后互动：{relation['last_interaction'][:10]}\n"
            f"特别备注：{relation['custom_note'] or '无'}"
        )
        
        ctx.add_return("reply", [response])
        ctx.prevent_default()

    @handler(command="/调整好感度")
    async def handle_admin_command(self, ctx: EventContext):
        """管理员调整命令"""
        if not self.is_admin(ctx.event.sender_id):
            ctx.add_return("reply", ["你没有权限执行此操作"])
            return
        
        try:
            _, target_id, delta, *reason = ctx.event.text_message.split()
            reason = " ".join(reason) or "管理员调整"
            self.update_score(target_id, int(delta), reason)
            await self.save_data()
            
            ctx.add_return("reply", [f"已调整用户 {target_id} 的好感度：{delta}"])
        except:
            ctx.add_return("reply", ["命令格式错误，示例：/调整好感度 123456 +5 理由"])

    def is_admin(self, user_id: str) -> bool:
        """简易管理员验证"""
        return str(user_id) in ["你的QQ号", "管理员QQ号"]

    def __del__(self):
        """插件卸载时保存数据"""
        import asyncio
        asyncio.run(self.save_data())
