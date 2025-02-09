# GroupMemoryMini

<!--
## 插件开发者详阅

### 开始

此仓库是 LangBot 插件模板，您可以直接在 GitHub 仓库中点击右上角的 "Use this template" 以创建你的插件。  
接下来按照以下步骤修改模板代码：

#### 修改模板代码

- 修改此文档顶部插件名称信息
- 将此文档下方的`<插件发布仓库地址>`改为你的插件在 GitHub· 上的地址
- 补充下方的`使用`章节内容
- 修改`main.py`中的`@register`中的插件 名称、描述、版本、作者 等信息
- 修改`main.py`中的`MyPlugin`类名为你的插件类名
- 将插件所需依赖库写到`requirements.txt`中
- 根据[插件开发教程](https://docs.langbot.app/plugin/dev/tutor.html)编写插件代码
- 删除 README.md 中的注释内容


#### 发布插件

推荐将插件上传到 GitHub 代码仓库，以便用户通过下方方式安装。   
欢迎[提issue](https://github.com/RockChinQ/LangBot/issues/new?assignees=&labels=%E7%8B%AC%E7%AB%8B%E6%8F%92%E4%BB%B6&projects=&template=submit-plugin.yml&title=%5BPlugin%5D%3A+%E8%AF%B7%E6%B1%82%E7%99%BB%E8%AE%B0%E6%96%B0%E6%8F%92%E4%BB%B6)，将您的插件提交到[插件列表](https://github.com/stars/RockChinQ/lists/qchatgpt-%E6%8F%92%E4%BB%B6)

下方是给用户看的内容，按需修改
-->

## 安装

配置完成 [LangBot](https://github.com/RockChinQ/LangBot) 主程序后使用管理员账号向机器人发送命令即可安装：

```
!plugin get https://github.com/Klein-Luckary/GroupMemoryMini.git
```
或查看详细的[插件安装说明](https://docs.langbot.app/plugin/plugin-intro.html#%E6%8F%92%E4%BB%B6%E7%94%A8%E6%B3%95)

## 使用

请在prompt中加入例如
你是一个具备人际关系管理能力的AI，请注意：
1. 根据用户评价分数调整回复语气
2. 在适当的时候使用(评价值：±N)标记调整分数
3. 特别关注用户的特别备注信息等指示。
- （可修改和扩充）
- 
- V0.4增加了记录互动次数和互动时间
- V0.5增加了用户指令/查看关系
- V0.6已经实现了存档和自修复（卸载的时候请手动保存插件的date内文件）
- V0.7修复了组群并发触发的错误识别人物bug
- V0.8增加了管理员指令
- /修改用户 <用户ID> 的评价分为 <分值>：修改指定用户的评价分。
- /增加标签 <用户ID> <标签>：为指定用户添加标签。
- /删除标签 <用户ID>：移除指定用户的标签。
- V0.9完善了后台日志方便观察。
- V1.0可以在main.py增加默认管理员了。
- 
- 如果报错json相关请不用理睬只是没有创建过该用户的数据会自修复
- 
- 非常低配的伪记忆。
- 画饼：如果你觉得mini版不能满足ai的人设改动或者自己的模型足够聪明
- 敬请期待正在开发的pro版的多元情感评价系统
