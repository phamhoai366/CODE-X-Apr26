"""Streamlit RAG chatbot for Excel, CSV, and PDF files using Ollama."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

import numpy as np
import pandas as pd
import requests
import streamlit as st
from pypdf import PdfReader


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "180"))
TOP_K = int(os.getenv("RAG_TOP_K", "5"))
SUPPORTED_EXTENSIONS = {"csv", "xls", "xlsx", "pdf"}


@dataclass(frozen=True)
class DocumentChunk:
    """A searchable piece of source content."""

    source: str
    location: str
    text: str

    @property
    def label(self) -> str:
        return f"{self.source} - {self.location}"


def normalize_extension(file_name: str) -> str:
    """Return the lowercase extension without the leading dot."""

    return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""


def dataframe_to_text(df: pd.DataFrame, source: str, location: str) -> str:
    """Convert tabular data to compact text while preserving columns and rows."""

    cleaned = df.dropna(how="all").fillna("")
    if cleaned.empty:
        return f"Nguồn: {source}\nVị trí: {location}\nKhông có dữ liệu."

    preview = cleaned.to_markdown(index=False)
    return f"Nguồn: {source}\nVị trí: {location}\n{preview}"


def read_csv(uploaded_file) -> list[DocumentChunk]:
    """Read a CSV file using common Vietnamese/Windows encodings."""

    raw = uploaded_file.getvalue()
    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "utf-8", "cp1258", "cp1252", "latin1"):
        try:
            df = pd.read_csv(BytesIO(raw), sep=None, engine="python", encoding=encoding)
            text = dataframe_to_text(df, uploaded_file.name, "CSV")
            return chunk_text(text, uploaded_file.name, "CSV")
        except Exception as exc:  # Pandas needs fallback attempts for unknown CSV formats.
            last_error = exc

    raise ValueError(f"Không đọc được CSV {uploaded_file.name}: {last_error}")


def read_excel(uploaded_file) -> list[DocumentChunk]:
    """Read every sheet from an Excel workbook."""

    chunks: list[DocumentChunk] = []
    sheets = pd.read_excel(BytesIO(uploaded_file.getvalue()), sheet_name=None)

    for sheet_name, df in sheets.items():
        location = f"Sheet {sheet_name}"
        text = dataframe_to_text(df, uploaded_file.name, location)
        chunks.extend(chunk_text(text, uploaded_file.name, location))

    return chunks


def read_pdf(uploaded_file) -> list[DocumentChunk]:
    """Extract text from each text-based PDF page."""

    reader = PdfReader(BytesIO(uploaded_file.getvalue()))
    chunks: list[DocumentChunk] = []

    for page_index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        page_text = f"Nguồn: {uploaded_file.name}\nVị trí: Trang {page_index}\n{text}"
        chunks.extend(chunk_text(page_text, uploaded_file.name, f"Trang {page_index}"))

    if not chunks:
        raise ValueError(
            f"PDF {uploaded_file.name} không có text layer. Hãy OCR file trước khi upload."
        )

    return chunks


def load_uploaded_files(uploaded_files) -> list[DocumentChunk]:
    """Load all supported uploaded files into chunks."""

    all_chunks: list[DocumentChunk] = []

    for uploaded_file in uploaded_files:
        extension = normalize_extension(uploaded_file.name)
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Định dạng không hỗ trợ: {uploaded_file.name}")

        if extension == "csv":
            all_chunks.extend(read_csv(uploaded_file))
        elif extension in {"xls", "xlsx"}:
            all_chunks.extend(read_excel(uploaded_file))
        elif extension == "pdf":
            all_chunks.extend(read_pdf(uploaded_file))

    return all_chunks


def chunk_text(text: str, source: str, location: str) -> list[DocumentChunk]:
    """Split text into overlapping chunks for retrieval."""

    compact_text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(compact_text) <= CHUNK_SIZE:
        return [DocumentChunk(source=source, location=location, text=compact_text)]

    chunks: list[DocumentChunk] = []
    start = 0
    chunk_number = 1

    while start < len(compact_text):
        end = min(start + CHUNK_SIZE, len(compact_text))
        split_at = compact_text.rfind("\n", start, end)
        if split_at <= start + CHUNK_SIZE // 2:
            split_at = end

        chunk = compact_text[start:split_at].strip()
        if chunk:
            chunk_location = f"{location}, đoạn {chunk_number}"
            chunks.append(DocumentChunk(source=source, location=chunk_location, text=chunk))
            chunk_number += 1

        if split_at >= len(compact_text):
            break
        start = max(0, split_at - CHUNK_OVERLAP)

    return chunks


def ollama_embed(texts: Iterable[str]) -> np.ndarray:
    """Create embeddings with Ollama, supporting current and legacy endpoints."""

    text_list = list(texts)
    payload = {"model": EMBED_MODEL, "input": text_list}
    response = requests.post(f"{OLLAMA_BASE_URL}/api/embed", json=payload, timeout=120)

    if response.status_code == 404:
        embeddings = ollama_legacy_embed(text_list)
    else:
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings")

    if not embeddings:
        raise ValueError("Ollama không trả về embeddings. Kiểm tra embedding model đã được pull chưa.")

    return np.array(embeddings, dtype=np.float32)


def ollama_legacy_embed(texts: list[str]) -> list[list[float]]:
    """Fallback to Ollama's legacy /api/embeddings endpoint for older servers."""

    embeddings: list[list[float]] = []
    for text in texts:
        payload = {"model": EMBED_MODEL, "prompt": text}
        # response = requests.post(f"{OLLAMA_BASE_URL}/api/embeddings", json=payload, timeout=120)
        response = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        embedding = response.json().get("embedding")
        if not embedding:
            raise ValueError(
                "Ollama không trả về embedding từ /api/embeddings. "
                "Hãy kiểm tra model embedding hoặc nâng cấp Ollama."
            )
        embeddings.append(embedding)

    return embeddings


def retrieve_context(question: str, chunks: list[DocumentChunk], embeddings: np.ndarray) -> list[tuple[DocumentChunk, float]]:
    """Return the most relevant chunks for a question using cosine similarity."""

    question_embedding = ollama_embed([question])[0]
    chunk_norms = np.linalg.norm(embeddings, axis=1)
    question_norm = np.linalg.norm(question_embedding)
    similarities = embeddings @ question_embedding / (chunk_norms * question_norm + 1e-10)
    top_indices = np.argsort(similarities)[::-1][:TOP_K]

    return [(chunks[index], float(similarities[index])) for index in top_indices]


def build_prompt(question: str, context_chunks: list[tuple[DocumentChunk, float]]) -> str:
    """Build a grounded Vietnamese prompt for Ollama."""

    context = "\n\n".join(
        f"[Nguồn {index}: {chunk.label}, điểm liên quan {score:.3f}]\n{chunk.text}"
        for index, (chunk, score) in enumerate(context_chunks, start=1)
    )

    return f"""
Bạn là chatbot phân tích dữ liệu nội bộ. Chỉ trả lời dựa trên phần NGỮ CẢNH bên dưới.
Nếu dữ liệu không đủ để kết luận, hãy nói rõ là chưa tìm thấy thông tin trong file đã nạp.
Trả lời bằng tiếng Việt, ngắn gọn, có thể liệt kê bullet nếu cần. Khi dùng thông tin, hãy nhắc tên nguồn.

NGỮ CẢNH:
{context}

CÂU HỎI:
{question}
""".strip()


def ollama_generate(prompt: str) -> str:
    """Generate an answer from Ollama."""

    payload = {
        "model": CHAT_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    response = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=180)
    response.raise_for_status()
    return response.json().get("response", "").strip()


def files_fingerprint(uploaded_files) -> str:
    """Create a stable fingerprint for the current uploads."""

    digest = hashlib.sha256()
    for uploaded_file in uploaded_files:
        digest.update(uploaded_file.name.encode("utf-8"))
        digest.update(uploaded_file.getvalue())
    return digest.hexdigest()


def initialize_state() -> None:
    """Initialize Streamlit session state."""

    st.session_state.setdefault("chunks", [])
    st.session_state.setdefault("embeddings", None)
    st.session_state.setdefault("fingerprint", None)
    st.session_state.setdefault("messages", [])


def main() -> None:
    """Render the Streamlit app."""

    st.set_page_config(page_title="Ollama Data Chatbot", page_icon="🤖", layout="wide")
    initialize_state()

    st.title("🤖 Chatbot học dữ liệu Excel, CSV, PDF bằng Ollama")
    st.caption(
        f"Ollama: `{OLLAMA_BASE_URL}` · Chat model: `{CHAT_MODEL}` · Embedding model: `{EMBED_MODEL}`"
    )

    with st.sidebar:
        st.header("1. Nạp dữ liệu")
        uploaded_files = st.file_uploader(
            "Chọn file Excel, CSV hoặc PDF",
            type=sorted(SUPPORTED_EXTENSIONS),
            accept_multiple_files=True,
        )

        if st.button("📚 Học dữ liệu từ file", type="primary", disabled=not uploaded_files):
            try:
                current_fingerprint = files_fingerprint(uploaded_files)
                with st.spinner("Đang đọc file và tạo embeddings bằng Ollama..."):
                    chunks = load_uploaded_files(uploaded_files)
                    embeddings = ollama_embed(chunk.text for chunk in chunks)

                st.session_state.chunks = chunks
                st.session_state.embeddings = embeddings
                st.session_state.fingerprint = current_fingerprint
                st.session_state.messages = []
                st.success(f"Đã học {len(chunks)} đoạn dữ liệu từ {len(uploaded_files)} file.")
            except Exception as exc:
                st.error(f"Lỗi khi học dữ liệu: {exc}")

        st.header("2. Trạng thái")
        st.write(f"Số đoạn đã học: **{len(st.session_state.chunks)}**")
        st.write(f"Top K truy xuất: **{TOP_K}**")
        st.info("Nếu đổi file, hãy bấm lại nút học dữ liệu trước khi hỏi.")

    if not st.session_state.chunks or st.session_state.embeddings is None:
        st.warning("Hãy upload file và bấm **Học dữ liệu từ file** để bắt đầu.")
        return

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Hỏi về dữ liệu đã nạp...")
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Đang tìm dữ liệu liên quan và hỏi Ollama..."):
                context_chunks = retrieve_context(
                    question,
                    st.session_state.chunks,
                    st.session_state.embeddings,
                )
                answer = ollama_generate(build_prompt(question, context_chunks))

            st.markdown(answer)
            with st.expander("Nguồn dữ liệu đã dùng"):
                for chunk, score in context_chunks:
                    st.markdown(f"**{chunk.label}** · điểm liên quan `{score:.3f}`")
                    st.text(chunk.text[:1000])

            st.session_state.messages.append({"role": "assistant", "content": answer})
        except Exception as exc:
            error_message = f"Không thể trả lời: {exc}"
            st.error(error_message)
            st.session_state.messages.append({"role": "assistant", "content": error_message})


if __name__ == "__main__":
    main()
