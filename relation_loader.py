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
        self.default_prompt_path = Path("data/prompts/default_prompt.txt")  # 默认 Bot 设定文件
        self.relation_data = {}

    async def initialize(self):
        await self.load_data()

    async def load_data(self):
        try:
            if self.data_path.exists():
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    self.relation_data = json.load(f)
        except Exception as e:
            self.ap.logger.error(f"加载关系数据失败: {str(e)}")
            self.relation_data = {}

    async def load(self):
        """加载默认 Bot 设定，并追加用户关系提示"""
        try:
            # 加载默认 Bot 设定
            if self.default_prompt_path.exists():
                with open(self.default_prompt_path, 'r', encoding='utf-8') as f:
                    default_prompt = f.read().strip()
                    if default_prompt:
                        self.prompts.append(
                            entities.Prompt(
                                role="system",
                                content=default_prompt,
                                priority=1000  # 默认设定优先级最高
                            )
                        )

            # 获取当前会话上下文
            session = self.ap.provider.current_session
            
            if not session or not session.sender_id:
                return
                
            user_id = str(session.sender_id)
            relation = self.relation_data.get(user_id, {
                "evaluation": 50,
                "custom_note": "",
                "interaction_count": 0,
                "last_interaction": datetime.now().isoformat()
            })

            # 追加用户关系提示
            prompt_text = (
                f"[用户关系档案]\n"
                f"用户ID: {user_id}\n"
                f"综合评分: {relation['evaluation']}/100\n"
                f"特殊标签: {relation['custom_note'] or '无'}\n"
                f"历史互动: {relation['interaction_count']}次\n"
                f"最后活跃: {relation['last_interaction'][:19]}"
            )

            self.prompts.append(
                entities.Prompt(
                    role="system",
                    content=prompt_text,
                    priority=500  # 用户关系提示优先级较低
                )
            )
        except Exception as e:
            self.ap.logger.error(f"生成关系提示失败: {str(e)}")
