"""查看文档的分片详情。

用法:
  uv run python -m scripts.inspect_chunks <workspace_id> [doc_id]

不传 doc_id 时列出该 workspace 所有文档及分片数。
传了 doc_id 时展示该文档所有分片的详细内容。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.storage.vector_store import VectorStore

DATA_DIR = os.getenv("DATA_DIR", "./data")


def main():
    if len(sys.argv) < 2:
        print("用法: uv run python -m scripts.inspect_chunks <workspace_id> [doc_id]")
        sys.exit(1)

    workspace_id = sys.argv[1]
    doc_id = sys.argv[2] if len(sys.argv) > 2 else None

    vector_store = VectorStore(f"{DATA_DIR}/chroma")

    try:
        collection = vector_store._get_existing_collection(workspace_id)
    except Exception:
        print(f"❌ workspace '{workspace_id}' 的 collection 不存在")
        sys.exit(1)

    total = collection.count()
    print(f"📦 workspace={workspace_id}, 总分片数={total}\n")

    # 获取所有分片
    where_filter = {"doc_id": doc_id} if doc_id else None
    results = collection.get(where=where_filter, include=["documents", "metadatas"])

    if not results["ids"]:
        print("未找到分片" + (f" (doc_id={doc_id})" if doc_id else ""))
        return

    # 按 doc_id 分组统计
    doc_groups: dict[str, list[int]] = {}
    for i, meta in enumerate(results["metadatas"]):
        did = meta.get("doc_id", "unknown")
        doc_groups.setdefault(did, []).append(i)

    if not doc_id:
        # 概览模式：列出每个文档的分片数
        print("── 文档分片概览 ──")
        for did, indices in sorted(doc_groups.items()):
            filename = results["metadatas"][indices[0]].get("filename", "?")
            print(f"  📄 {filename} (doc_id={did[:8]}…) → {len(indices)} 个分片")
        print(f"\n💡 查看具体分片: uv run python -m scripts.inspect_chunks {workspace_id} <doc_id>")
        return

    # 详情模式：展示每个分片
    print(f"── 文档分片详情 (doc_id={doc_id[:8]}…) ──\n")
    # 按 chunk_index 排序
    indexed = sorted(
        zip(results["documents"], results["metadatas"]),
        key=lambda pair: pair[1].get("chunk_index", 0),
    )
    for i, (text, meta) in enumerate(indexed):
        chapter = meta.get("chapter_title", "")
        section = meta.get("section_title", "")
        page_start = meta.get("page_start", 0)
        page_end = meta.get("page_end", 0)
        location = " > ".join(filter(None, [chapter, section]))
        page_info = f"p.{page_start}-{page_end}" if page_start else ""

        print(f"{'─' * 60}")
        print(f"分片 #{i} | {location} {page_info} | {len(text)} 字符")
        print(f"{'─' * 60}")
        print(text[:500] + ("…" if len(text) > 500 else ""))
        print()


if __name__ == "__main__":
    main()
