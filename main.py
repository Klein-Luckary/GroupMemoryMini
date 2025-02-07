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
    description="基于关系管理系统的轻量伪记忆系统",
    version="0.2",
    author="KL"
)
class RelationManager(BasePlugin):
    def __init__(self, host: APIHost):
        self.host = host
        self.data_path = Path("plugins/GroupMemoryMini/data/relation_data.json")
        self.relation_data = {}
        # 匹配AI回复中的评价值调整标记（支持多种格式）（可修改）
        self.pattern = re.compile(r"\评价值([+-]?\d+)\|评价值\s*[：:]\s*([+-]?\d+)")

    async def initialize(self):
        """异步初始化"""
        await self.load_data()

    async def load_data(self):
        """安全加载数据（自动修复损坏文件）"""
        try:
            if self.data_path.exists():
                # 读取文件内容并验证完整性
                raw_content = self.data_path.read_text(encoding="utf-8")
                
                # 检查空文件
                if not raw_content.strip():
                    raise json.JSONDecodeError("Empty file", doc="", pos=0)
                    
                # 尝试解析JSON
                self.relation_data = json.loads(raw_content)
                self.ap.logger.info("关系数据加载成功")
                
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # 备份损坏文件
            corrupt_path = self.data_path.with_name(f"corrupt_{datetime.now().strftime('%Y%m%d%H%M')}_relation_data.json")
            self.data_path.rename(corrupt_path)
        
            # 初始化空数据
            self.relation_data = {}
            self.ap.logger.error(f"数据文件损坏，已备份至 {corrupt_path}，初始化新数据")
            
        except Exception as e:
            self.ap.logger.error(f"未知加载错误: {str(e)}")
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
        """获取用户数据（带自动修复）"""
        try:
            data = self.relation_data.get(user_id, {})
            
            # 数据完整性检查
            required_keys = {"score", "history", "last_interaction", "custom_note"}
            if not required_keys.issubset(data.keys()):
                raise KeyError("Missing required keys")
            
            # 类型校验
            if not isinstance(data["score"], int):
                data["score"] = int(data["score"])
            
            # 数值范围限制
            data["score"] = max(0, min(100, data["score"]))
        
            # 时间格式修复
            if "T" not in data["last_interaction"]:
                data["last_interaction"] = datetime.now().isoformat()
            
            # 更新数据结构
            self.relation_data[user_id] = data
            return data
        
        except Exception as e:
            self.ap.logger.warning(f"用户 {user_id} 数据损坏，已重置: {str(e)}")
            self.relation_data[user_id] = self._init_user_data()
            return self.relation_data[user_id]

    def _init_user_data(self) -> dict:
        """初始化用户数据结构模板"""
        return {
            "score": 50,
            "history": [],
            "last_interaction": datetime.now().isoformat(),
            "custom_note": ""
        }
        
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
                    self.ap.logger.warning(f"无效的评价值数值: {value}")

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
                self.ap.logger.info(f"用户 {user_id} 评价值变化: {actual_adjustment}, 当前: {new_score}")

                # 更新回复内容
                ctx.event.response_text = cleaned_response.strip() or "[评价值已更新]"

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_query(self, ctx: EventContext):
        """处理查询请求"""
        event = ctx.event
        
        if event.text_message.strip() == "/查看关系":
            user_id = str(event.sender_id)
            relation = self.get_relation(user_id)
            
            report = (
                f"【关系状态】\n"
                f"• 当前评价值：{relation['score']}/100\n"
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
