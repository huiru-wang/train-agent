#!/usr/bin/env python3
"""Inspect ChromaDB collections and chunks for debugging.

Usage:
    uv run python scripts/inspect_chunks.py                     # list all collections
    uv run python scripts/inspect_chunks.py <workspace_id>      # list chunks in workspace
    uv run python scripts/inspect_chunks.py <workspace_id> -d <doc_id>  # chunks of a specific doc
    uv run python scripts/inspect_chunks.py <workspace_id> -q "query"   # semantic search test
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import chromadb

DATA_DIR = os.getenv("DATA_DIR", "./data")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")


def get_client():
    if not os.path.isdir(CHROMA_DIR):
        print(f"ChromaDB directory not found: {CHROMA_DIR}")
        sys.exit(1)
    return chromadb.PersistentClient(path=CHROMA_DIR)


def list_collections(client):
    collections = client.list_collections()
    if not collections:
        print("No collections found.")
        return
    print(f"Found {len(collections)} collection(s):\n")
    print(f"{'Collection':<40} {'Chunks':>8}")
    print("-" * 50)
    for col in collections:
        print(f"{col.name:<40} {col.count():>8}")


def inspect_collection(client, workspace_id, doc_id=None):
    name = f"ws_{workspace_id}"
    try:
        collection = client.get_collection(name)
    except Exception:
        print(f"Collection '{name}' not found.")
        sys.exit(1)

    where = {"doc_id": doc_id} if doc_id else None
    total = collection.count()
    print(f"Collection: {name}  (total chunks: {total})")
    if doc_id:
        print(f"Filter: doc_id={doc_id}")
    print()

    results = collection.get(where=where, include=["documents", "metadatas"])
    ids = results["ids"]
    docs = results["documents"]
    metas = results["metadatas"]

    if not ids:
        print("No chunks found.")
        return

    # Group by doc_id
    by_doc: dict[str, list] = {}
    for i, cid in enumerate(ids):
        did = metas[i].get("doc_id", "?")
        by_doc.setdefault(did, []).append((cid, docs[i], metas[i]))

    for did, chunks in sorted(by_doc.items()):
        filename = chunks[0][2].get("filename", "?")
        print(f"--- doc_id: {did}  filename: {filename}  ({len(chunks)} chunks) ---")
        for cid, text, meta in sorted(chunks, key=lambda x: x[2].get("chunk_index", 0)):
            idx = meta.get("chunk_index", "?")
            section = meta.get("section_title", "")
            page = f"p{meta.get('page_start', '?')}-{meta.get('page_end', '?')}"
            preview = text[:120].replace("\n", "\\n")
            print(f"  [{idx:>4}] id={cid[:12]}.. {page:>8}  section={section}")
            print(f"         {preview}...")
        print()


def search_test(client, workspace_id, query, top_k=5, doc_id=None):
    name = f"ws_{workspace_id}"
    try:
        collection = client.get_collection(name)
    except Exception:
        print(f"Collection '{name}' not found.")
        sys.exit(1)

    where = {"doc_id": doc_id} if doc_id else None
    print(f"Search: '{query}'  top_k={top_k}  workspace={workspace_id}")
    if doc_id:
        print(f"Filter: doc_id={doc_id}")
    print()

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    for i, text in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        dist = results["distances"][0][i] if results.get("distances") else "?"
        idx = meta.get("chunk_index", "?")
        section = meta.get("section_title", "")
        filename = meta.get("filename", "?")
        preview = text[:200].replace("\n", "\\n")
        print(f"[{i+1}] distance={dist:.4f}  chunk={idx}  file={filename}  section={section}")
        print(f"    {preview}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Inspect ChromaDB data")
    parser.add_argument("workspace_id", nargs="?", help="Workspace ID")
    parser.add_argument("-d", "--doc-id", help="Filter by document ID")
    parser.add_argument("-q", "--query", help="Semantic search query")
    parser.add_argument("-k", "--top-k", type=int, default=5, help="Number of search results")
    args = parser.parse_args()

    client = get_client()

    if not args.workspace_id:
        list_collections(client)
    elif args.query:
        search_test(client, args.workspace_id, args.query, args.top_k, args.doc_id)
    else:
        inspect_collection(client, args.workspace_id, args.doc_id)


if __name__ == "__main__":
    main()
