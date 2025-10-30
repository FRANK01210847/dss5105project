from __future__ import annotations
import os, tempfile
from typing import Optional, Tuple, Union, Callable
from pathlib import Path
from dotenv import load_dotenv

# 从项目根目录加载 .env
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=ROOT / ".env")

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain


# ---------- 基础工具 ----------
def _pdf_to_path(pdf_file: Union[str, bytes, bytearray, "UploadedFile"]) -> str:
    """将上传的 PDF 保存为临时文件"""
    if isinstance(pdf_file, str) and os.path.exists(pdf_file):
        return pdf_file
    data = pdf_file.read() if hasattr(pdf_file, "read") else (
        bytes(pdf_file) if isinstance(pdf_file, (bytes, bytearray)) else None
    )
    if data is None:
        raise ValueError("Unsupported pdf_file type.")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(data)
    tmp.flush()
    tmp.close()
    return tmp.name


def _ensure_key(explicit: Optional[str]) -> str:
    """确保 OPENAI_API_KEY 存在"""
    load_dotenv(dotenv_path=ROOT / ".env", override=False)
    key = explicit or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("Lack of OPENAI_API_KEY; please configure it in .env or enter it in the sidebar.")
    return key


# ---------- 构建与加载 ----------
def build_vectorstore_from_pdf(
    pdf_file,
    *,
    chunk_size=1000,
    chunk_overlap=200,
    openai_api_key: Optional[str] = None
) -> FAISS:
    """从 PDF 文件构建向量数据库"""
    path = _pdf_to_path(pdf_file)
    try:
        docs = PyPDFLoader(path).load()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap, length_function=len
        )
        chunks = splitter.split_documents(docs)
        embeddings = OpenAIEmbeddings(openai_api_key=_ensure_key(openai_api_key))
        return FAISS.from_documents(chunks, embeddings)
    finally:
        try:
            if os.path.exists(path) and "tmp" in os.path.dirname(path):
                os.unlink(path)
        except Exception:
            pass


def save_vectorstore(vectorstore: FAISS, save_dir: str) -> None:
    """保存向量数据库到本地"""
    os.makedirs(save_dir, exist_ok=True)
    vectorstore.save_local(save_dir)


def load_vectorstore(load_dir: str, openai_api_key: Optional[str] = None) -> FAISS:
    """加载本地向量数据库"""
    embeddings = OpenAIEmbeddings(openai_api_key=_ensure_key(openai_api_key))
    return FAISS.load_local(load_dir, embeddings, allow_dangerous_deserialization=True)


# ---------- 构建对话链 ----------
def create_conversation_chain(
    vectorstore: FAISS,
    *,
    temperature=0.2,
    max_tokens=1500,
    model_name="gpt-4o-mini",
    openai_api_key: Optional[str] = None
) -> Tuple[ConversationalRetrievalChain, ChatOpenAI, ConversationBufferMemory, Callable]:
    """
    创建 Conversational Retrieval Chain（带记忆）
    并返回安全包装调用函数 safe_invoke
    """
    llm = ChatOpenAI(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=_ensure_key(openai_api_key)
    )
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="answer"
    )

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever = vectorstore.as_retriever(
            search_kwargs={
                "k": 5,  # 稍微增加检索数量
                "score_threshold": 0.5  # 显著降低相似度阈值
            }
        ),
        memory=memory,
        return_source_documents=True
    )

    # ✅ 包装安全调用函数（防止 "answer" 缺失）
    def safe_invoke(inputs):
        res = chain(inputs)
        if "answer" not in res and "result" in res:
            res["answer"] = res["result"]
        return res

    return chain, llm, memory, safe_invoke
