import streamlit as st
import httpx
import pandas as pd
import plotly.express as px
from datetime import datetime
import json


class AdminDashboard:
    def __init__(self, base_url="http://54.254.143.80:8000/api/v1"):
        self.base_url = base_url
        self.client = httpx.Client()

    def get_api_keys_info(self):
        """获取所有API key的信息"""
        response = self.client.get(f"{self.base_url}/api_key/list_keys")
        if response.status_code == 200:
            return response.json()
        st.error(f"获取API Keys失败: {response.status_code} - {response.text}")
        return {}

    def get_conversation_history(self, api_key):
        """获取指定API key的对话历史"""
        # 构造请求体
        request_data = {
            "client_idx": 0,  # 这里可以是任意值，因为我们要获取所有对话
            "conversation_type": "basic",  # 默认使用basic类型
            "api_key": api_key,
        }

        try:
            response = self.client.post(
                f"{self.base_url}/conversation_history/get_conversation_histories",
                headers={"Authorization": api_key},
                json=request_data,
            )

            from loguru import logger

            # 检查响应状态码
            if response.status_code == 204:
                st.info("暂无对话历史")
                return []

            if response.status_code != 200:
                st.error(
                    f"获取对话历史失败: {response.status_code} - {response.content}"
                )
                return []

            # 确保响应内容不为空
            if not response.content:
                st.info("响应内容为空")
                return []

            try:
                conversations = response.json()
                # 处理每个对话的时间格式
                for conv in conversations:
                    if "messages" in conv:
                        for msg in conv["messages"]:
                            if "timestamp" in msg:
                                msg["timestamp"] = self.format_conversation_time(
                                    msg["timestamp"]
                                )
                return conversations
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析错误: {str(e)}")
                st.error(f"解析响应数据失败: {str(e)}")
                return []

        except Exception as e:
            from traceback import format_exc

            logger.error(format_exc())
            st.error(f"请求失败: {str(e)}")
            return []

    def get_cookie_status(self):
        """获取所有Cookie的状态"""
        response = self.client.get(f"{self.base_url}/cookie/list_all_cookies")
        if response.status_code == 200:
            return response.json()
        st.error(f"获取Cookie状态失败: {response.status_code} - {response.text}")
        return []

    def get_all_api_keys(self):
        """获取所有API keys的基本信息"""
        response = self.client.get(f"{self.base_url}/api_key/list_keys")
        if response.status_code == 200:
            return response.json()
        st.error(f"获取API Keys失败: {response.status_code} - {response.text}")
        return {}

    def format_conversation_time(self, timestamp):
        """格式化对话时间"""
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return timestamp

    def get_api_key_type(self, api_key):
        """获取API key的类型"""
        api_keys_info = self.get_all_api_keys()
        if api_key in api_keys_info:
            return api_keys_info[api_key]["key_type"]
        return "basic"  # 默认返回basic类型


def render_conversation(conversation):
    """渲染单个对话内容"""
    st.markdown("---")

    # 对话信息头部
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**对话ID**: `{conversation['conversation_id']}`")
    with col2:
        st.markdown(f"**模型**: {conversation.get('model', 'Unknown')}")

    # 对话内容
    for msg in conversation["messages"]:
        is_assistant = msg["role"] == "assistant"

        # 创建两列布局，根据发送者使用不同的对齐方式
        col1, col2 = st.columns([6, 6])

        if is_assistant:
            with col1:
                st.markdown(
                    f"""
                    <div style="background-color: #f0f2f6; padding: 10px; border-radius: 10px; margin: 5px 0;">
                        🤖 <b>Assistant</b><br>
                        {msg['content']}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            with col2:
                st.markdown(
                    f"""
                    <div style="background-color: #e1f5fe; padding: 10px; border-radius: 10px; margin: 5px 0;">
                        👤 <b>User</b><br>
                        {msg['content']}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def main():
    st.set_page_config(page_title="Claude API 管理面板", layout="wide")
    dashboard = AdminDashboard()

    # 创建session state来存储当前选中的API key和页面状态
    if "current_api_key" not in st.session_state:
        st.session_state.current_api_key = None
    if "current_page" not in st.session_state:
        st.session_state.current_page = "main"

    st.title("Claude API 管理面板")

    # 创建侧边栏
    st.sidebar.title("导航")

    # 如果在对话详情页面，添加返回按钮
    if st.session_state.current_page == "conversation_detail":
        if st.sidebar.button("← 返回API Keys列表"):
            st.session_state.current_page = "main"
            st.session_state.current_api_key = None
            st.rerun()

    page = st.sidebar.radio("选择页面", ["API Keys 概览", "对话历史", "Cookie 状态"])

    if page == "API Keys 概览":
        render_api_keys_overview(dashboard)
    elif page == "对话历史":
        if st.session_state.current_page == "main":
            render_api_keys_list(dashboard)
        else:
            render_conversation_detail(dashboard)
    elif page == "Cookie 状态":
        render_cookie_status(dashboard)


def render_api_keys_list(dashboard):
    """渲染API keys列表页面"""
    st.header("API Keys 列表")

    api_keys_info = dashboard.get_all_api_keys()

    if api_keys_info:
        # 创建API keys表格
        api_keys_data = []
        for key, info in api_keys_info.items():
            api_keys_data.append(
                {
                    "API Key": key,
                    "类型": info["key_type"],
                    "状态": "有效" if info["is_key_valid"] else "已过期",
                    "最后使用时间": info["last_usage_time"],
                    "当前使用量": info["current_usage"],
                    "总使用量": info["usage"],
                }
            )

        df = pd.DataFrame(api_keys_data)

        # 使用列表形式展示API keys
        for idx, row in df.iterrows():
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.write(f"**API Key**: `{row['API Key']}`")
                st.write(f"类型: {row['类型']}")
            with col2:
                st.write(f"状态: {row['状态']}")
                st.write(f"使用量: {row['当前使用量']}/{row['总使用量']}")
            with col3:
                if st.button("查看对话", key=f"view_{row['API Key']}"):
                    st.session_state.current_api_key = row["API Key"]
                    st.session_state.current_page = "conversation_detail"
                    st.rerun()
            st.markdown("---")


def render_conversation_detail(dashboard):
    """渲染对话详情页面"""
    api_key = st.session_state.current_api_key
    st.header(f"对话历史 - {api_key}")

    conversations = dashboard.get_conversation_history(api_key)

    if conversations:
        # 创建对话列表
        st.subheader("对话列表")

        # 添加搜索和排序功能
        col1, col2 = st.columns(2)
        with col1:
            search_term = st.text_input("搜索对话内容", key="search_conversations")
        with col2:
            sort_order = st.selectbox(
                "排序方式", ["最新优先", "最早优先"], key="sort_conversations"
            )

        # 筛选对话
        if search_term:
            conversations = [
                conv
                for conv in conversations
                if any(
                    search_term.lower() in msg["content"].lower()
                    for msg in conv["messages"]
                )
            ]

        # 排序对话
        if sort_order == "最早优先":
            conversations.reverse()

        # 使用选项卡展示对话
        for idx, conv in enumerate(conversations):
            # 获取对话的预览内容
            preview = (
                conv["messages"][0]["content"][:100] + "..."
                if conv["messages"]
                else "空对话"
            )
            timestamp = (
                conv["messages"][-1]["timestamp"] if conv["messages"] else "未知时间"
            )

            with st.expander(f"对话 {idx+1} - {timestamp}"):
                render_conversation(conv)
    else:
        st.info("暂无对话记录")


def render_api_keys_overview(dashboard):
    """渲染API Keys概览页面"""
    st.header("API Keys 使用情况")

    api_keys_info = dashboard.get_api_keys_info()

    if api_keys_info:
        # 将数据转换为DataFrame以便展示
        data = []
        for key, info in api_keys_info.items():
            data.append(
                {
                    "API Key": key,
                    "类型": info["key_type"],
                    "当前使用量": info["current_usage"],
                    "总使用量": info["usage"],
                    "使用限制": info["usage_limit"],
                    "最后使用时间": info["last_usage_time"],
                    "过期时间": info["expire_time"],
                    "状态": "有效" if info["is_key_valid"] else "已过期",
                }
            )

        df = pd.DataFrame(data)

        # 添加统计信息
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("总API Keys数量", len(df))
        with col2:
            st.metric("有效Keys数量", len(df[df["状态"] == "有效"]))
        with col3:
            st.metric("已过期Keys数量", len(df[df["状态"] == "已过期"]))

        # 显示详细数据表格
        st.subheader("详细数据")
        st.dataframe(df)

        # 添加使用量统计图表
        st.subheader("使用量统计")
        fig1 = px.bar(
            df, x="API Key", y="当前使用量", color="类型", title="API Keys 当前使用量"
        )
        st.plotly_chart(fig1)

        # 添加使用量占比饼图
        fig2 = px.pie(
            df, names="类型", values="当前使用量", title="不同类型API Keys使用量占比"
        )
        st.plotly_chart(fig2)


def render_cookie_status(dashboard):
    """渲染Cookie状态页面"""
    st.header("Cookie 状态概览")

    cookies = dashboard.get_cookie_status()
    if cookies:
        # 将数据转换为DataFrame
        data = []
        for cookie in cookies:
            data.append(
                {
                    "Cookie Key": cookie["cookie_key"],
                    "类型": cookie["type"],
                    "账号": cookie["account"],
                    "使用类型": cookie.get("usage_type", "未知"),
                }
            )

        df = pd.DataFrame(data)

        # 添加统计信息
        col1, col2 = st.columns(2)
        with col1:
            st.metric("总Cookie数量", len(df))
        with col2:
            st.metric("Plus Cookie数量", len(df[df["类型"] == "plus"]))

        # 显示详细数据表格
        st.subheader("Cookie详细信息")
        st.dataframe(df)

        # 添加Cookie类型分布饼图
        st.subheader("Cookie 类型分布")
        fig = px.pie(df, names="类型", title="Cookie 类型分布")
        st.plotly_chart(fig)

        # 添加使用类型分布图
        st.subheader("Cookie 使用类型分布")
        fig2 = px.bar(df, x="使用类型", color="类型", title="Cookie 使用类型分布")
        st.plotly_chart(fig2)


if __name__ == "__main__":
    main()
