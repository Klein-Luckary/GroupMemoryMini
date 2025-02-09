# plugins/GroupMemoryMini/relation_loader.py
from pkg.provider.sysprompt.loader import loader_class, PromptLoader
from pkg.provider.sysprompt import entities
from pkg.plugin.context import APIHost
from datetime import datetime
import json
from pathlib import Path

@loader_class("relation_loader")
class RelationPromptLoader(PromptLoader):
    def __init__(self, ap):
        super().__init__(ap)
        self.data_path = Path("plugins/GroupMemoryMini/data/relation_data.json")
        self.relation_data = {}

    async def initialize(self):
        """初始化时加载用户关系数据"""
        await self.load_data()

    async def load_data(self):
        """加载用户关系数据"""
        try:
            if self.data_path.exists():
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    self.relation_data = json.load(f)
        except Exception as e:
            self.ap.logger.error(f"加载关系数据失败: {str(e)}")
            self.relation_data = {}

    async def load(self):
        """生成用户关系提示并插入到系统提示中"""
        try:
            # 获取当前会话上下文
            session = self.ap.provider.current_session
            
            if not session or not session.sender_id:
                self.ap.logger.warning("无法获取会话或用户ID，跳过提示生成")
                return
                
            user_id = str(session.sender_id)
            relation = self.relation_data.get(user_id, {
                "evaluation": 50,
                "custom_note": "",
                "interaction_count": 0,
                "last_interaction": datetime.now().isoformat()
            })

            # 生成用户关系提示
            prompt_text = (
                f"[用户关系档案]\n"
                f"用户ID: {user_id}\n"
                f"综合评分: {relation['evaluation']}/100\n"
                f"特殊标签: {relation['custom_note'] or '无'}\n"
                f"历史互动: {relation['interaction_count']}次\n"
                f"最后活跃: {relation['last_interaction'][:19]}"
            )

            # 插入到prompts列表的最前面
            self.prompts.insert(
                0,  # 插入到最前面
                entities.Prompt(
                    role="system",
                    content=prompt_text,
                    priority=1000  # 最高优先级
                )
            )

            self.ap.logger.debug(f"已插入用户关系提示: {prompt_text}")
        except Exception as e:
            self.ap.logger.error(f"生成关系提示失败: {str(e)}")
        except Exception as e:
            self.ap.logger.error(f"生成关系提示失败: {str(e)}")
