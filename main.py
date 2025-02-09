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
    version="1.0",  # 更新版本号
    author="Klein_Luckary"
)
class RelationManager(BasePlugin):
    def __init__(self, host: APIHost):
        super().__init__(host)
        self.data_path = Path("plugins/GroupMemoryMini/data/relation_data.json")
        self.relation_data = {}
        self.pattern = re.compile(r"评价值([+-]?\d+)|评价值\s*[：:]\s*([+-]?\d+)")
        
        # 默认管理员列表
        self.admin_users = ["123456789"]  # 替换为实际的管理员用户ID

    async def initialize(self):
        """插件初始化时加载数据"""
        await self.load_data()

    async def load_data(self):
        """加载用户关系数据"""
        try:
            if self.data_path.exists():
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        self.relation_data = {}
                    else:
                        self.relation_data = json.loads(content)
        except json.JSONDecodeError as e:
            self.ap.logger.error(f"JSON 解析失败: {str(e)}")
            self.relation_data = {}
        except Exception as e:
            self.ap.logger.error(f"加载数据失败: {str(e)}")
            self.relation_data = {}

    async def save_data(self):
        """保存用户关系数据"""
        try:
            temp_path = self.data_path.with_suffix(".tmp")
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self.relation_data, f, ensure_ascii=False, indent=2)
            temp_path.replace(self.data_path)
        except Exception as e:
            self.ap.logger.error(f"保存数据失败: {str(e)}")

    def get_relation(self, user_id: str) -> dict:
        """获取或初始化用户关系数据"""
        return self.relation_data.setdefault(user_id, {
            "evaluation": 200,
            "history": [],
            "last_interaction": datetime.now().isoformat(),
            "custom_note": "",
            "interaction_count": 0
        })

    def is_admin(self, user_id: str) -> bool:
        """检查用户是否为管理员"""
        return user_id in self.admin_users

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

        # 处理管理员指令
        if self.is_admin(user_id):
            if ctx.event.text_message.startswith("/修改用户"):
                await self.handle_modify_evaluation(ctx)
                return
            elif ctx.event.text_message.startswith("/增加标签"):
                await self.handle_add_tag(ctx)
                return
            elif ctx.event.text_message.startswith("/删除标签"):
                await self.handle_remove_tag(ctx)
                return

        # 普通用户指令
        if ctx.event.text_message.strip() == "/查看关系":
            report = (
                f"【关系状态】\n"
                f"• 当前评分：{relation['evaluation']}/1000\n"
                f"• 互动次数：{relation['interaction_count']}次\n"
                f"• 最后互动：{relation['last_interaction'][:19]}\n"
                f"• 特别备注：{relation['custom_note'] or '暂无'}"
            )
            ctx.event.reply = [report]
            ctx.prevent_default()

        # 动态修改默认提示
        if hasattr(ctx.event, 'alter'):
            relation_prompt = (
                f"[用户关系档案]\n"
                f"用户ID: {user_id}\n"
                f"综合评分: {relation['evaluation']}/1000\n"
                f"特殊标签: {relation['custom_note'] or '无'}\n"
                f"历史互动: {relation['interaction_count']}次\n"
                f"最后活跃: {relation['last_interaction'][:19]}"
            )
            ctx.event.alter = f"{relation_prompt}\n\n{ctx.event.alter or ctx.event.text_message}"

    async def handle_modify_evaluation(self, ctx: EventContext):
        """处理修改评价分指令"""
        try:
            parts = ctx.event.text_message.split()
            target_user = parts[1]
            new_evaluation = int(parts[3])
            
            if not target_user or not new_evaluation:
                raise ValueError("参数错误")
            
            relation = self.get_relation(target_user)
            old_evaluation = relation["evaluation"]
            relation["evaluation"] = max(0, min(1000, new_evaluation))
            relation["history"].append({
                "timestamp": datetime.now().isoformat(),
                "adjustment": new_evaluation - old_evaluation,
                "reason": "管理员手动调整"
            })
            await self.save_data()
            
            ctx.event.reply = [f"用户 {target_user} 的评价分已从 {old_evaluation} 修改为 {new_evaluation}。"]
            ctx.prevent_default()
        except Exception as e:
            ctx.event.reply = [f"修改评价分失败: {str(e)}"]
            ctx.prevent_default()

    async def handle_add_tag(self, ctx: EventContext):
        """处理增加标签指令"""
        try:
            parts = ctx.event.text_message.split()
            target_user = parts[1]
            tag = parts[2]
            
            if not target_user or not tag:
                raise ValueError("参数错误")
            
            relation = self.get_relation(target_user)
            if "custom_note" not in relation:
                relation["custom_note"] = ""
            relation["custom_note"] = tag
            await self.save_data()
            
            ctx.event.reply = [f"已为用户 {target_user} 添加标签: {tag}。"]
            ctx.prevent_default()
        except Exception as e:
            ctx.event.reply = [f"增加标签失败: {str(e)}"]
            ctx.prevent_default()

    async def handle_remove_tag(self, ctx: EventContext):
        """处理删除标签指令"""
        try:
            parts = ctx.event.text_message.split()
            target_user = parts[1]
            
            if not target_user:
                raise ValueError("参数错误")
            
            relation = self.get_relation(target_user)
            if "custom_note" in relation:
                relation["custom_note"] = ""
            await self.save_data()
            
            ctx.event.reply = [f"已移除用户 {target_user} 的标签。"]
            ctx.prevent_default()
        except Exception as e:
            ctx.event.reply = [f"删除标签失败: {str(e)}"]
            ctx.prevent_default()

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
            new_evaluation = max(0, min(1000, relation["evaluation"] + total_adjustment))
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
                f"[系统提示] 评价值已更新，当前为 {new_evaluation}/1000。"
            )
            
    def __del__(self):
        pass
