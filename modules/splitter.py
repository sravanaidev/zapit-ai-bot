from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


def split_documents(
    docs: list[Document],
    chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    chunks = splitter.split_documents(docs)
    print(f"Split {len(docs)} document(s) into {len(chunks)} chunks")
    return chunks
